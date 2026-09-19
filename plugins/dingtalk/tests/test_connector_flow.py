"""Channel product flow with a simulated platform and channel; no live delivery claim."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from opsmesh_plugin_sdk.cards import CardTemplate
from opsmesh_plugin_sdk.contracts import AutomationStreamEvent
from opsmesh_plugin_sdk.services import PluginServicesClient

from opsmesh_dingtalk.channel import parse_callback, parse_message
from opsmesh_dingtalk.configuration import ChannelConfiguration
from opsmesh_dingtalk.connector import Connector


def test_message_stream_card_callback_and_recovery():
    async def flow():
        workspace_id, install_id, automation_id, event_id = (uuid4() for _ in range(4))
        store = {}
        accepted = {}
        output = []
        callbacks = []
        failure = True
        revoked = False
        phase = "working"
        config = ChannelConfiguration(
            automation_id=automation_id,
            corp_id="corp",
            card=CardTemplate(
                key="task",
                channel="dingtalk",
                template_id="published.schema",
                parameters={"markdown": "text", "status": "status"},
                actions={"pause": {"label": "Pause", "action": "pause"}},
            ),
        )

        def transport(request):
            path = request.url.path
            body = json.loads(request.content) if request.content else None
            if "/storage/" in path:
                key = path.rsplit("/", 1)[1]
                if request.method == "GET":
                    return (
                        httpx.Response(200, json=store[key])
                        if key in store
                        else httpx.Response(404)
                    )
                previous = store.get(key, {"revision": 0})
                if body["expected_revision"] != previous["revision"]:
                    return httpx.Response(409)
                store[key] = {
                    "key": key,
                    "revision": previous["revision"] + 1,
                    "value": body["value"],
                }
                return httpx.Response(200, json=store[key])
            if path.endswith("/logs"):
                assert "secret" not in request.content.decode()
                return httpx.Response(204)
            if revoked:
                return httpx.Response(403)
            if request.method == "POST" and path.endswith("/events"):
                if body["sender_id"] != "corp:employee1":
                    return httpx.Response(403)
                if body["action"] != "start":
                    callbacks.append(body)
                if body["event_id"] in accepted:
                    assert accepted[body["event_id"]] == body
                accepted[body["event_id"]] = body
                return httpx.Response(
                    202,
                    json={
                        "id": str(event_id),
                        "automation_id": str(automation_id),
                        "external_event_id": body["event_id"],
                        "conversation_id": body["conversation_id"],
                        "reply_delivery_id": None,
                        "error_code": None,
                        "status": "pending",
                        "task_id": None,
                    },
                )
            if path.endswith("/stream"):
                kinds = [("output.text", {"text": "preview"}), ("tool.started", {"name": "logs"})]
                if phase == "completed":
                    kinds = [
                        ("output.completed", {"output": {"answer": "done"}}),
                        ("stream.completed", {}),
                    ]
                else:
                    kinds += [("checkpoint", {}), ("stream.reconnect", {})]
                frames = [
                    AutomationStreamEvent(
                        event_id=event_id, task_id=None, kind=kind, cursor="1-0", data=data
                    ).model_dump_json()
                    for kind, data in kinds
                ]
                return httpx.Response(
                    200,
                    content="\n".join(frames) + "\n",
                    headers={"content-type": "application/x-ndjson"},
                )
            return httpx.Response(
                200,
                json={
                    "event": {
                        "id": str(event_id),
                        "automation_id": str(automation_id),
                        "external_event_id": "message-1",
                        "conversation_id": "conversation",
                        "reply_delivery_id": None,
                        "error_code": None,
                        "status": "dispatched",
                        "task_id": None,
                    },
                    "output": {},
                    "task_status": "running",
                    "pending_actions": [],
                    "notification_sequence": 0,
                },
            )

        class Channel:
            async def create(self, track_id, staff_id, cfg, values):
                output.append((track_id, staff_id, values))

            async def update(self, track_id, values):
                nonlocal failure
                if failure:
                    failure = False
                    raise ConnectionError("simulated delivery outage")
                output.append((track_id, values))

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport), base_url="https://platform.example/api/v1/"
        ) as http:
            host = PluginServicesClient(http, workspace_id, install_id)
            connector = Connector(host, Channel(), config)
            raw = {
                "senderCorpId": "corp",
                "senderStaffId": "employee1",
                "senderNick": "Employee",
                "msgId": "message-1",
                "conversationId": "group",
                "conversationType": "2",
                "msgtype": "text",
                "text": {"content": "Investigate order 123"},
                "createAt": 1000000,
            }
            incoming = parse_message(raw, config)
            assert await connector.receive(incoming) == await connector.receive(incoming)
            with pytest.raises(httpx.HTTPStatusError):
                await connector.receive(
                    parse_message({**raw, "senderStaffId": "employee2"}, config)
                )
            key = connector.key(incoming.message)
            await connector.process(await host.read(key))
            failed = await host.read(key)
            assert failed.value["cursor"] == "0-0"
            assert failed.value["attempts"] == 1
            # The process can restart; persisted record retains the original event and card ID.
            from opsmesh_plugin_sdk.services import StoreWrite

            await host.write(
                key,
                StoreWrite(
                    expected_revision=failed.revision, value={**failed.value, "retry_at": 0}
                ),
            )
            connector = Connector(host, Channel(), config)
            await connector.process(await host.read(key))
            current = await host.read(key)
            assert current.value["cursor"] == "1-0"
            assert len([item for item in output if len(item) == 3]) == 1
            track_id = output[0][0]
            stamp = datetime.now(UTC)
            payload = {
                "corpId": "corp",
                "userId": "employee1",
                "outTrackId": track_id,
                "content": json.dumps({"cardPrivateData": {"params": {"action": "pause"}}}),
            }
            track, sender, action = parse_callback(payload, config)
            await connector.callback(track, sender, action, "callback-1", stamp)
            await connector.callback(track, sender, action, "callback-1", stamp)
            assert callbacks[0] == callbacks[1]
            with pytest.raises(ValueError):
                await connector.callback(track, "corp:employee2", action, "callback-2", stamp)
            phase = "completed"
            failure = True
            await connector.process(await host.read(key))
            pending = await host.read(key)
            assert not pending.value["complete"]
            await host.write(
                key,
                StoreWrite(
                    expected_revision=pending.revision, value={**pending.value, "retry_at": 0}
                ),
            )
            await connector.process(await host.read(key))
            assert (await host.read(key)).value["complete"]
            assert "done" in output[-1][-1]["markdown"]
            revoked = True
            with pytest.raises(httpx.HTTPStatusError):
                await connector.callback(track, sender, action, "callback-3", stamp)

    asyncio.run(flow())
