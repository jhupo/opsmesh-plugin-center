"""Connector ingress over the authenticated public API; HTTP is owned by HTTPX."""

from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from opsmesh_plugin_sdk.messaging.contracts import (
    AcceptedEvent,
    ApprovalDecision,
    ApprovalReceipt,
    AttachmentUpload,
    AutomationStreamEvent,
    EventState,
    IncomingMessage,
    MessageAttachment,
)


class AutomationClient:
    def __init__(self, client: httpx.Client, workspace_id: UUID, automation_id: UUID) -> None:
        """Client base_url must include /api/v1/ and its auth must carry a workspace token."""
        self._client = client
        self._path = f"workspaces/{workspace_id}/automations/{automation_id}/events"

    def submit(self, message: IncomingMessage) -> AcceptedEvent:
        response = self._client.post(self._path, json=message.model_dump(mode="json"))
        response.raise_for_status()
        return AcceptedEvent.model_validate(response.json())

    def state(self, event_id: UUID) -> EventState:
        response = self._client.get(f"{self._path}/{event_id}")
        response.raise_for_status()
        return EventState.model_validate(response.json())


class AsyncAutomationClient:
    """Caller owns HTTPX lifecycle and retries; normal stream rollover is automatic."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        workspace_id: UUID,
        automation_id: UUID,
        *,
        install_id: UUID | None = None,
    ) -> None:
        self._client = client
        root = (
            f"plugin-runtime/{workspace_id}/{install_id}"
            if install_id
            else f"workspaces/{workspace_id}"
        )
        self._path = f"{root}/automations/{automation_id}/events"

    async def submit(self, message: IncomingMessage) -> AcceptedEvent:
        response = await self._client.post(self._path, json=message.model_dump(mode="json"))
        response.raise_for_status()
        return AcceptedEvent.model_validate(response.json())

    async def state(self, event_id: UUID) -> EventState:
        response = await self._client.get(f"{self._path}/{event_id}")
        response.raise_for_status()
        return EventState.model_validate(response.json())

    async def events(
        self,
        event_id: UUID,
        *,
        cursor: str = "0-0",
        once: bool = False,
    ) -> AsyncIterator[AutomationStreamEvent]:
        while True:
            rollover = False
            async with self._client.stream(
                "GET",
                f"{self._path}/{event_id}/stream",
                params={"cursor": cursor, "once": str(once).lower()},
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0] != "application/x-ndjson":
                    raise ValueError("Unexpected automation stream content type")
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    frame = AutomationStreamEvent.model_validate_json(line)
                    if frame.event_id != event_id:
                        raise ValueError("Stream event does not match subscription")
                    cursor = frame.cursor
                    yield frame
                    if frame.kind in {"stream.completed", "stream.revoked"}:
                        return
                    rollover = frame.kind == "stream.reconnect"
            if once:
                return
            if not rollover:
                raise httpx.ReadError(
                    "Automation stream ended without a terminal or rollover frame"
                )


class MessageServicesClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def upload_attachment(
        self,
        automation_id: UUID,
        metadata: AttachmentUpload,
        content: bytes,
    ) -> MessageAttachment:
        if not 0 < len(content) <= 20 * 1024 * 1024:
            raise ValueError("Attachment must contain at most 20 MiB")
        response = await self._client.post(
            f"{self._path}/automations/{automation_id}/attachments",
            data={"metadata": metadata.model_dump_json()},
            files={"file": (metadata.filename, content, metadata.content_type)},
        )
        response.raise_for_status()
        return MessageAttachment.model_validate(response.json())

    async def decide_approval(
        self,
        automation_id: UUID,
        event_id: UUID,
        approval_id: UUID,
        decision: ApprovalDecision,
    ) -> ApprovalReceipt:
        response = await self._client.post(
            f"{self._path}/automations/{automation_id}/events/{event_id}"
            f"/approvals/{approval_id}/decision",
            json=decision.model_dump(mode="json"),
        )
        response.raise_for_status()
        return ApprovalReceipt.model_validate(response.json())
