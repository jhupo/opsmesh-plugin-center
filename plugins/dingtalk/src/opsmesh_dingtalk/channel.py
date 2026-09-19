"""Official DingTalk SDK boundary; no platform policy or hand-written HTTP protocol."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import dingtalk_stream
from alibabacloud_dingtalk.card_1_0 import models as cards
from alibabacloud_dingtalk.card_1_0.client import Client
from alibabacloud_dingtalk.oauth2_1_0.client import Client as OAuthClient
from alibabacloud_dingtalk.oauth2_1_0.models import GetAccessTokenRequest
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions
from opsmesh_plugin_sdk.contracts import IncomingMessage

from opsmesh_dingtalk.configuration import ChannelConfiguration


@dataclass(frozen=True)
class ChannelMessage:
    message: IncomingMessage
    staff_id: str


def parse_message(data: dict[str, Any], config: ChannelConfiguration) -> ChannelMessage:
    incoming = dingtalk_stream.ChatbotMessage.from_dict(data)
    if (
        incoming.sender_corp_id != config.corp_id
        or not incoming.sender_staff_id
        or incoming.message_type != "text"
        or not incoming.message_id
        or not incoming.conversation_id
        or not data.get("createAt")
    ):
        raise ValueError("Unsupported message or unverified enterprise sender")
    text = str(incoming.text.content).strip()
    staff_id = str(incoming.sender_staff_id)
    sender_id = f"{config.corp_id}:{staff_id}"
    # Partition group conversations by sender: the group is never a shared authorization scope.
    conversation = str(incoming.conversation_id)
    import hashlib

    conversation_id = hashlib.sha256(f"{conversation}:{sender_id}".encode()).hexdigest()
    return ChannelMessage(
        IncomingMessage(
            event_id=str(incoming.message_id),
            conversation_id=conversation_id,
            sender_id=sender_id,
            occurred_at=datetime.fromtimestamp(int(data["createAt"]) / 1000, UTC),
            contract_version=config.contract_version,
            data={
                config.question_field: text,
                config.user_field: {"id": sender_id, "name": str(incoming.sender_nick)},
            },
        ),
        staff_id,
    )


def parse_callback(data: dict[str, Any], config: ChannelConfiguration) -> tuple[str, str, str]:
    incoming = dingtalk_stream.CardCallbackMessage.from_dict(data)
    if incoming.corp_id != config.corp_id or not incoming.user_id or not incoming.card_instance_id:
        raise ValueError("Unverified card sender")
    private = incoming.content.get("cardPrivateData", {})
    action = private.get("params", {}).get("action")
    if not isinstance(action, str) or action not in config.card.actions:
        raise ValueError("Unsupported card action")
    return str(incoming.card_instance_id), f"{config.corp_id}:{incoming.user_id}", action


class DingTalkCards:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = ""
        self.expires_at = 0.0
        self.oauth = OAuthClient(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.client = Client(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.options = RuntimeOptions(
            read_timeout=15000, connect_timeout=5000, autoretry=True, max_attempts=3
        )

    async def create(
        self,
        track_id: str,
        staff_id: str,
        config: ChannelConfiguration,
        values: dict[str, str],
    ) -> None:
        async with self.authorization() as token:
            # Always deliver to the requesting employee's robot conversation, including group input.
            # out_track_id is stable across crashes/retries and used by DingTalk for idempotency.
            await self.client.create_and_deliver_with_options_async(
                cards.CreateAndDeliverRequest(
                    out_track_id=track_id,
                    card_template_id=config.card.template_id,
                    card_data=cards.CreateAndDeliverRequestCardData(card_param_map=values),
                    callback_type="STREAM",
                    user_id_type=1,
                    open_space_id=f"dtv1.card//IM_ROBOT.{staff_id}",
                    im_robot_open_deliver_model=cards.CreateAndDeliverRequestImRobotOpenDeliverModel(
                        space_type="IM_ROBOT",
                        robot_code=self.client_id,
                    ),
                    im_robot_open_space_model=cards.CreateAndDeliverRequestImRobotOpenSpaceModel(
                        support_forward=False,
                    ),
                ),
                cards.CreateAndDeliverHeaders(x_acs_dingtalk_access_token=token),
                self.options,
            )

    async def update(self, track_id: str, values: dict[str, str]) -> None:
        async with self.authorization() as token:
            await self.client.update_card_with_options_async(
                cards.UpdateCardRequest(
                    out_track_id=track_id,
                    card_data=cards.UpdateCardRequestCardData(card_param_map=values),
                ),
                cards.UpdateCardHeaders(x_acs_dingtalk_access_token=token),
                self.options,
            )

    @asynccontextmanager
    async def authorization(self) -> AsyncIterator[str]:
        token = await self.access_token()
        try:
            yield token
        except Exception:
            # A revoked/expired channel token must be refreshed before durable retry.
            self.expires_at = 0
            raise

    async def access_token(self) -> str:
        if self.token and time.monotonic() < self.expires_at:
            return self.token
        response = await self.oauth.get_access_token_with_options_async(
            GetAccessTokenRequest(app_key=self.client_id, app_secret=self.client_secret),
            {},
            self.options,
        )
        if not response.body.access_token or not response.body.expire_in:
            raise RuntimeError("DingTalk token unavailable")
        self.token = str(response.body.access_token)
        self.expires_at = time.monotonic() + max(0, int(response.body.expire_in) - 300)
        return self.token


class SDKLogFilter(logging.Filter):
    """Upstream logs can include credential responses and message bodies; keep codes only."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "dingtalk.sdk_event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True
