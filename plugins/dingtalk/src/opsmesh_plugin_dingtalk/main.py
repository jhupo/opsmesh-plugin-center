import asyncio
import logging
import multiprocessing
import signal
import time
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from types import FrameType
from typing import Any

import dingtalk_stream
import httpx
from opsmesh_plugin_sdk.client import PluginClient

from opsmesh_plugin_dingtalk.channel import (
    DingTalkCards,
    SDKLogFilter,
    parse_callback,
    parse_message,
)
from opsmesh_plugin_dingtalk.configuration import ChannelConfiguration, Settings
from opsmesh_plugin_dingtalk.connector import Connector

logger = logging.getLogger("opsmesh_plugin_dingtalk")


class MessageHandler(dingtalk_stream.CallbackHandler):  # type: ignore[misc]
    def __init__(self, connector: Connector) -> None:
        super().__init__()
        self.connector = connector

    async def process(self, callback: Any) -> tuple[int, object]:
        try:
            incoming = parse_message(callback.data, self.connector.config)
            await self.connector.receive(incoming)
            return dingtalk_stream.AckMessage.STATUS_OK, "accepted"
        except (ValueError, KeyError, TypeError):
            logger.warning("message.rejected")
            return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, "unsupported message"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 401, 403, 404, 422}:
                logger.warning("message.denied")
                return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, "access denied"
            logger.warning("message.retry")
            return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "retry later"
        except Exception:
            logger.warning("message.retry")
            return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "retry later"


class CardHandler(dingtalk_stream.CallbackHandler):  # type: ignore[misc]
    def __init__(self, connector: Connector) -> None:
        super().__init__()
        self.connector = connector

    async def process(self, callback: Any) -> tuple[int, object]:
        try:
            track_id, sender_id, action, approval_id = parse_callback(
                callback.data, self.connector.config
            )
            if not callback.headers.message_id or callback.headers.time is None:
                raise ValueError("Missing stable callback identity")
            await self.connector.callback(
                track_id,
                sender_id,
                action,
                str(callback.headers.message_id),
                datetime.fromtimestamp(int(callback.headers.time) / 1000, UTC),
                approval_id=approval_id,
            )
            return dingtalk_stream.AckMessage.STATUS_OK, {
                "cardUpdateOptions": {"updateCardDataByKey": True},
                "cardData": {"cardParamMap": {}},
            }
        except (ValueError, KeyError, TypeError):
            logger.warning("card.action_rejected")
            return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, "action denied"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 401, 403, 404, 422}:
                logger.warning("card.action_denied")
                return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, "action denied"
            return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "retry later"
        except Exception:
            logger.warning("card.action_retry")
            return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "retry later"


async def deliver_forever(connector: Connector) -> None:
    refresh_at = 0.0
    while True:
        try:
            if time.monotonic() >= refresh_at:
                connector.config = ChannelConfiguration.model_validate(
                    await connector.host.configuration.read()
                )
                refresh_at = time.monotonic() + 30
            # Bounded store (512 records), stable snapshot avoids pagination shifts during deletion.
            rows = []
            for offset in range(0, 512, 100):
                page = await connector.host.storage.values(prefix="card:", offset=offset)
                rows.extend(page)
                if len(page) < 100:
                    break
            # One process handles its inbox serially; CAS leases also protect overlapping processes.
            for row in rows:
                await connector.process(row)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise RuntimeError(
                    "Plugin credential revoked or installation unavailable"
                ) from None
            logger.warning("platform.retry")
        except Exception:
            logger.warning("delivery.scan_failed")
        await asyncio.sleep(connector.config.poll_seconds)


async def run(settings: Settings, heartbeat: Connection) -> None:
    sdk_logger = logging.getLogger("dingtalk.connector")
    sdk_logger.addFilter(SDKLogFilter())
    stream = dingtalk_stream.DingTalkStreamClient(
        dingtalk_stream.Credential(settings.client_id, settings.client_secret.get_secret_value()),
        logger=sdk_logger,
    )
    async with httpx.AsyncClient(
        base_url=settings.platform_url,
        follow_redirects=False,
        headers={"Authorization": "Bearer " + settings.platform_token.get_secret_value()},
        timeout=httpx.Timeout(65, connect=5),
    ) as http:
        host = PluginClient(http, settings.workspace_id, settings.install_id)
        config = ChannelConfiguration.model_validate(await host.configuration.read())
        connector = Connector(
            host,
            DingTalkCards(settings.client_id, settings.client_secret.get_secret_value()),
            config,
        )
        messages, cards = MessageHandler(connector), CardHandler(connector)
        messages.logger, cards.logger = sdk_logger, sdk_logger
        stream.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, messages)
        stream.register_callback_handler(dingtalk_stream.CallbackHandler.TOPIC_CARD_CALLBACK, cards)
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(stream.start())
            tasks.create_task(deliver_forever(connector))
            tasks.create_task(keepalive(heartbeat))


async def keepalive(connection: Connection) -> None:
    while True:
        connection.send_bytes(b"alive")
        await asyncio.sleep(5)


def child(settings: Settings, heartbeat: Connection) -> None:
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run(settings, heartbeat))
    except Exception:
        logger.error("connector.worker_stopped")
        raise SystemExit(1) from None
    finally:
        heartbeat.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        settings = Settings.environment()
        context = multiprocessing.get_context("spawn")
        # The official Stream SDK performs synchronous connection I/O and catches cancellation.
        # A process boundary bounds hangs/shutdown without patching its protocol implementation.
        failures = 0
        while failures < 3:
            reader, writer = context.Pipe(duplex=False)
            worker = context.Process(target=child, args=(settings, writer), daemon=True)
            worker.start()
            writer.close()
            try:
                while worker.is_alive() and reader.poll(35):
                    try:
                        reader.recv_bytes()
                    except EOFError:
                        break
            finally:
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.kill()
                    worker.join(timeout=5)
                reader.close()
            failures += 1
            logger.warning("connector.worker_restart")
        raise RuntimeError("Connector restart budget exhausted")
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.error(
            "connector.stopped: check configuration, credentials and platform availability"
        )
        raise SystemExit(1) from None


def request_stop(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt
