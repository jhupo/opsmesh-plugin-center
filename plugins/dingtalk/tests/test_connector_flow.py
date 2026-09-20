"""Channel product flow with a simulated platform and channel; no live delivery claim."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from opsmesh_plugin_sdk.client import PluginClient
from opsmesh_plugin_sdk.messaging.contracts import AutomationStreamEvent

from opsmesh_plugin_dingtalk.cards import CardTemplate
from opsmesh_plugin_dingtalk.channel import parse_callback, parse_message
from opsmesh_plugin_dingtalk.configuration import ChannelConfiguration
from opsmesh_plugin_dingtalk.connector import Connector


@pytest.mark.parametrize("group_reply", [False, True])
@pytest.mark.parametrize("media", [None, "picture", "file", "audio"])
def test_message_stream_card_callback_and_recovery(group_reply, media):
    async def flow():
        workspace_id, install_id, automation_id, event_id = (uuid4() for _ in range(4))
        store = {}
        accepted = {}
        output = []
        callbacks = []
        failure = True
        revoked = False
        member = True
        readable = True
        task_id = uuid4()
        phase = "working"
        approval = uuid4()
        decisions = []
        config = ChannelConfiguration(
            automation_id=automation_id,
            corp_id="corp",
            allowed_attachment_kinds=["image", "file", "audio"],
            reply_mode="group_recipients" if group_reply else "sender_only",
            group_recipients={"group": ["employee1"]} if group_reply else {},
            card=CardTemplate(
                key="task",
                channel="dingtalk",
                template_id="published.schema",
                parameters={"markdown": "text", "status": "status"},
                actions={
                    "pause": {"label": "Pause", "action": "pause"},
                    "approve": {"label": "Approve", "action": "approve"},
                },
            ),
        )

        def transport(request):
            path = request.url.path
            if path.endswith("/attachments"):
                multipart = BytesParser(policy=policy.default).parsebytes(
                    b"Content-Type: "
                    + request.headers["content-type"].encode()
                    + b"\r\n\r\n"
                    + request.content
                )
                parts = {
                    part.get_param("name", header="content-disposition"): part
                    for part in multipart.iter_parts()
                }
                metadata = json.loads(parts["metadata"].get_payload(decode=True))
                binary = parts["file"].get_payload(decode=True)
                assert metadata["external_event_id"] == "message-1"
                assert metadata["sender_id"] == "corp:employee1"
                assert binary == b"media content"
                return httpx.Response(
                    201,
                    json={
                        "file_id": str(uuid5(NAMESPACE_URL, "media-1")),
                        "kind": metadata["kind"],
                        "filename": metadata["filename"],
                        "content_type": metadata["content_type"],
                        "size_bytes": len(binary),
                        "checksum_sha256": hashlib.sha256(binary).hexdigest(),
                        "transcript": metadata["transcript"],
                    },
                )
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
            if path.endswith("/permissions"):
                assert body["resource_id"] == str(task_id)
                return httpx.Response(200, json={"actions": ["read"] if readable else []})
            if path.endswith(f"/approvals/{approval}/decision"):
                assert body["sender_id"] == "corp:employee1"
                decisions.append(body)
                return httpx.Response(200, json={"id": str(approval), "status": "approved"})
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
                        "task_id": str(task_id),
                    },
                    "output": {},
                    "task_status": "running",
                    "pending_actions": (
                        [{"id": str(approval), "kind": "tool_execution", "risk_level": "high"}]
                        if phase == "approval"
                        else []
                    ),
                    "notification_sequence": 0,
                },
            )

        class Channel:
            async def download(self, attachment):
                types = {"image": "image/png", "file": "text/plain", "audio": "audio/amr"}
                assert attachment.download_code == "private-download-code"
                return b"media content", types[attachment.kind]

            async def create(self, track_id, staff_id, cfg, values, *, group_id, recipients):
                assert group_id == ("group" if group_reply else None)
                assert recipients == (["employee1"] if group_reply else [])
                output.append((track_id, staff_id, values))

            async def require_group_members(self, group_id, recipients):
                assert group_id == "group" and recipients == ["employee1"]
                if not member:
                    raise ValueError("Member removed")

            async def update(self, track_id, values):
                nonlocal failure
                if failure:
                    failure = False
                    raise ConnectionError("simulated delivery outage")
                output.append((track_id, values))

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport), base_url="https://platform.example/api/v1/"
        ) as http:
            host = PluginClient(http, workspace_id, install_id)
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
            if media is not None:
                raw.update(
                    {
                        "msgtype": media,
                        "content": {
                            "downloadCode": "private-download-code",
                            "fileName": "order.txt",
                            "recognition": "Investigate order 123",
                        },
                    }
                )
                incoming = parse_message(raw, config)
            assert await connector.receive(incoming) == await connector.receive(incoming)
            if media is None:
                with pytest.raises((httpx.HTTPStatusError, ValueError)):
                    await connector.receive(
                        parse_message({**raw, "senderStaffId": "employee2"}, config)
                    )
            key = connector.key(incoming.message)
            await connector.process(await host.storage.read(key))
            failed = await host.storage.read(key)
            assert failed.value["cursor"] == "0-0"
            assert failed.value["attempts"] == 1
            # The process can restart; persisted record retains the original event and card ID.
            from opsmesh_plugin_sdk.services.storage import StoreWrite

            await host.storage.write(
                key,
                StoreWrite(
                    expected_revision=failed.revision, value={**failed.value, "retry_at": 0}
                ),
            )
            connector = Connector(host, Channel(), config)
            await connector.process(await host.storage.read(key))
            current = await host.storage.read(key)
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
            track, sender, action, approval_id = parse_callback(payload, config)
            assert approval_id is None
            await connector.callback(track, sender, action, "callback-1", stamp)
            await connector.callback(track, sender, action, "callback-1", stamp)
            assert callbacks[0] == callbacks[1]
            with pytest.raises(ValueError):
                await connector.callback(track, "corp:employee2", action, "callback-2", stamp)
            phase = "approval"
            await connector.process(await host.storage.read(key))
            with pytest.raises(ValueError):
                await connector.callback(
                    track, sender, "approve", "approval-1", stamp, approval_id=uuid4()
                )
            for _ in range(2):
                assert (
                    await connector.callback(
                        track, sender, "approve", "approval-1", stamp, approval_id=approval
                    )
                    == approval
                )
            assert decisions[0] == decisions[1]
            if group_reply:
                before = len(output)
                member = False
                await connector.process(await host.storage.read(key))
                assert len(output) == before
                member = True
                readable = False
                row = await host.storage.read(key)
                await host.storage.write(
                    key,
                    StoreWrite(expected_revision=row.revision, value={**row.value, "retry_at": 0}),
                )
                await connector.process(await host.storage.read(key))
                assert len(output) == before
                readable = True
                row = await host.storage.read(key)
                await host.storage.write(
                    key,
                    StoreWrite(expected_revision=row.revision, value={**row.value, "retry_at": 0}),
                )
            phase = "completed"
            failure = True
            await connector.process(await host.storage.read(key))
            pending = await host.storage.read(key)
            assert not pending.value["complete"]
            await host.storage.write(
                key,
                StoreWrite(
                    expected_revision=pending.revision, value={**pending.value, "retry_at": 0}
                ),
            )
            await connector.process(await host.storage.read(key))
            assert (await host.storage.read(key)).value["complete"]
            assert "done" in output[-1][-1]["markdown"]
            revoked = True
            with pytest.raises(httpx.HTTPStatusError):
                await connector.callback(track, sender, action, "callback-3", stamp)

    asyncio.run(flow())
