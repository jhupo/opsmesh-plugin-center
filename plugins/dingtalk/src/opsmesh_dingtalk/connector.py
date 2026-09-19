"""Durable channel inbox and card outbox; task execution stays in OpsMesh."""

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from opsmesh_plugin_sdk.cards import CardTemplate
from opsmesh_plugin_sdk.contracts import IncomingMessage
from opsmesh_plugin_sdk.services import (
    ApprovalDecision,
    AttachmentUpload,
    PermissionQuery,
    PluginLog,
    PluginServicesClient,
    StoredValue,
    StoreWrite,
)
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_dingtalk.channel import ChannelMessage, RawAttachment
from opsmesh_dingtalk.configuration import ChannelConfiguration


class CardChannel(Protocol):
    async def create(
        self,
        track_id: str,
        staff_id: str,
        config: ChannelConfiguration,
        values: dict[str, str],
        *,
        group_id: str | None,
        recipients: list[str],
    ) -> None: ...
    async def update(self, track_id: str, values: dict[str, str]) -> None: ...
    async def require_group_members(self, group_id: str, recipients: list[str]) -> None: ...
    async def download(self, attachment: RawAttachment) -> tuple[bytes, str]: ...


class Delivery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: IncomingMessage
    staff_id: str
    group_id: str | None = None
    recipients: list[str] = Field(default_factory=list, max_length=20)
    automation_id: UUID
    event_id: UUID
    cursor: str = "0-0"
    text: str = ""
    status: str = "accepted"
    created: bool = False
    complete: bool = False
    blocked: bool = False
    attempts: int = 0
    retry_at: float = 0
    lease_owner: str = ""
    lease_until: float = 0
    expires_at: float
    template: dict[str, object] = Field(default_factory=dict)
    approval_id: UUID | None = None
    approval_text: str = ""
    presented_approvals: list[UUID] = Field(default_factory=list, max_length=32)


class Connector:
    def __init__(
        self, host: PluginServicesClient, channel: CardChannel, config: ChannelConfiguration
    ) -> None:
        self.host, self.channel, self.config = host, channel, config
        self.owner = uuid4().hex

    def key(self, message: IncomingMessage) -> str:
        return (
            "card:"
            + hashlib.sha256(
                f"{self.config.automation_id}:{message.sender_id}:{message.event_id}".encode()
            ).hexdigest()
        )

    async def receive(self, incoming: ChannelMessage) -> UUID:
        message = incoming.message
        group_id = None
        recipients: list[str] = []
        if self.config.reply_mode == "group_recipients":
            group_id = incoming.group_id
            recipients = self.config.group_recipients.get(group_id or "", [])
            if group_id is None or incoming.staff_id not in recipients:
                raise ValueError("Message is not in an approved group audience")
            await self.channel.require_group_members(group_id, recipients)
        if incoming.attachments:
            uploaded = []
            for slot, attachment in enumerate(incoming.attachments):
                content, content_type = await self.channel.download(attachment)
                uploaded.append(
                    await self.host.upload_attachment(
                        self.config.automation_id,
                        AttachmentUpload(
                            sender_id=message.sender_id,
                            external_event_id=message.event_id,
                            slot=slot,
                            kind=attachment.kind,
                            filename=attachment.filename,
                            content_type=content_type,
                            transcript=attachment.text,
                        ),
                        content,
                    )
                )
            message = message.model_copy(
                update={
                    "text": message.text
                    or next((item.text for item in incoming.attachments if item.text), ""),
                    "attachments": uploaded,
                }
            )
        accepted = await self.host.automation(self.config.automation_id).submit(message)
        key = self.key(message)
        current = await self.host.read(key)
        if current is None:
            delivery = Delivery(
                # The platform owns the accepted body. The bounded outbox only needs routing
                # metadata for controls; do not duplicate transcripts or attachments here.
                message=message.model_copy(
                    update={
                        "text": "",
                        "attachments": [],
                        "data": {self.config.question_field: ""},
                    }
                ),
                staff_id=incoming.staff_id,
                group_id=group_id,
                recipients=recipients,
                automation_id=self.config.automation_id,
                event_id=accepted.id,
                expires_at=time.time() + self.config.retention_hours * 3600,
                template=self.config.card.model_dump(mode="json"),
            )
            try:
                await self.host.write(
                    key, StoreWrite(expected_revision=0, value=delivery.model_dump(mode="json"))
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise
                current = await self.host.read(key)
                if (
                    current is None
                    or Delivery.model_validate(current.value).event_id != accepted.id
                ):
                    raise
        return accepted.id

    async def callback(
        self,
        track_id: str,
        sender_id: str,
        action_id: str,
        callback_id: str,
        occurred_at: datetime,
        *,
        approval_id: UUID | None = None,
    ) -> UUID:
        if not track_id.startswith("opsmesh_") or len(track_id) != 72:
            raise ValueError("Unknown card")
        row = await self.host.read("card:" + track_id[8:])
        if row is None:
            raise ValueError("Card expired")
        delivery = Delivery.model_validate(row.value)
        if (
            delivery.message.sender_id != sender_id
            or delivery.automation_id != self.config.automation_id
            or delivery.expires_at <= time.time()
            or delivery.blocked
        ):
            raise ValueError("Card action denied")
        if delivery.group_id is not None:
            state = await self.host.automation(delivery.automation_id).state(delivery.event_id)
            await self._authorize_audience(delivery, state.event.task_id)
        action = self.config.card.actions[action_id].action
        original = CardTemplate.model_validate(delivery.template).actions.get(action_id)
        if original is None or original.action != action:
            raise ValueError("Card action configuration changed")
        if action in {"approve", "reject"}:
            if approval_id is None or approval_id not in delivery.presented_approvals:
                raise ValueError("Approval was not presented on this card")
            receipt = await self.host.decide_approval(
                delivery.automation_id,
                delivery.event_id,
                approval_id,
                ApprovalDecision(sender_id=sender_id, decision=action),
            )
            return receipt.id
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("Unsupported task control")
        accepted = await self.host.automation(delivery.automation_id).submit(
            IncomingMessage(
                event_id="card:" + hashlib.sha256(callback_id.encode()).hexdigest(),
                conversation_id=delivery.message.conversation_id,
                sender_id=sender_id,
                occurred_at=occurred_at,
                contract_version=delivery.message.contract_version,
                action=action,
                reply_to_event_id=delivery.event_id,
                data=delivery.message.data,
            )
        )
        return accepted.id

    async def process(self, row: StoredValue) -> None:
        delivery = Delivery.model_validate(row.value)
        now = time.time()
        if delivery.complete and delivery.expires_at <= now:
            await self.host.delete(row.key, expected_revision=row.revision)
            return
        if (
            delivery.complete
            or delivery.blocked
            or delivery.retry_at > now
            or delivery.lease_until > now
        ):
            return
        delivery.lease_owner, delivery.lease_until = self.owner, now + 120
        try:
            row = await self.host.write(
                row.key,
                StoreWrite(expected_revision=row.revision, value=delivery.model_dump(mode="json")),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                return
            raise
        try:
            async with asyncio.timeout(90):
                await self._deliver(row, delivery)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                delivery.blocked = True
                delivery.status, delivery.text = "access_revoked", ""
            elif exc.response.status_code == 409:
                return  # Lost lease/CAS: another owner will recover the record.
            await self._failed(row, delivery)
        except Exception:
            # Preserve durable state without leaking vendor exception bodies or credentials.
            await self._failed(row, delivery)

    async def _failed(self, row: StoredValue, delivery: Delivery) -> None:
        # A terminal frame is not a delivered result. Retain retryability until the update succeeds.
        delivery.complete = False
        delivery.attempts += 1
        delivery.retry_at = time.time() + min(300, 2 ** min(delivery.attempts, 8))
        delivery.lease_owner, delivery.lease_until = "", 0
        if delivery.attempts >= 12:
            delivery.blocked = True
        await self.host.write(
            row.key,
            StoreWrite(expected_revision=row.revision, value=delivery.model_dump(mode="json")),
        )
        await self.host.log(
            PluginLog(
                level="warning",
                code="card.delivery_failed",
                event_id=delivery.event_id,
                metadata={"attempts": delivery.attempts, "blocked": delivery.blocked},
            )
        )

    async def _deliver(self, row: StoredValue, delivery: Delivery) -> None:
        client = self.host.automation(delivery.automation_id)
        # State access and every stream batch revalidate both installation and human authority.
        initial = await client.state(delivery.event_id)
        if delivery.group_id is not None and initial.event.task_id is None:
            if initial.event.status in {"failed", "rejected", "skipped", "completed"}:
                delivery.blocked = True
            delivery.lease_owner, delivery.lease_until = "", 0
            await self.host.write(
                row.key,
                StoreWrite(expected_revision=row.revision, value=delivery.model_dump(mode="json")),
            )
            return
        await self._authorize_audience(delivery, initial.event.task_id)
        track_id = "opsmesh_" + row.key[5:]
        if not delivery.created:
            snapshot_config = self.config.model_copy(
                update={"card": CardTemplate.model_validate(delivery.template)}
            )
            await self.channel.create(
                track_id,
                delivery.staff_id,
                snapshot_config,
                self._render(delivery),
                group_id=delivery.group_id,
                recipients=delivery.recipients,
            )
            delivery.created = True
        cursor = delivery.cursor
        async for frame in client.events(delivery.event_id, cursor=cursor, once=True):
            cursor = frame.cursor
            if frame.kind == "stream.revoked":
                delivery.blocked = True
                delivery.status, delivery.text = "access_revoked", ""
                delivery.approval_id, delivery.approval_text = None, ""
                delivery.presented_approvals = []
                break
            if frame.kind in {"stream.reset", "output.reset"}:
                delivery.text = ""
            elif frame.kind == "output.text":
                delivery.text = _card_text(str(frame.data.get("text", "")))
                delivery.status = "working"
            elif frame.kind.startswith("tool."):
                delivery.status = frame.kind + ":" + str(frame.data.get("name", ""))[:40]
            elif frame.kind == "approval.required":
                delivery.status = "approval_required"
            elif frame.kind == "output.completed":
                delivery.text = _card_text(
                    json.dumps(frame.data.get("output", {}), ensure_ascii=False)
                )
                delivery.status = "completed"
            elif frame.kind in {"output.rejected", "task.failed", "task.cancelled"}:
                delivery.text, delivery.status = "", frame.kind
            elif frame.kind == "state":
                status = frame.data.get("task_status")
                if status:
                    delivery.status = str(status)
                event = frame.data.get("event")
                if isinstance(event, dict) and event.get("status") in {"rejected", "skipped"}:
                    delivery.status = str(event["status"])
            elif frame.kind == "stream.completed":
                delivery.complete = True
        # Authorization is checked again immediately before sending any newly collected content.
        if not delivery.blocked:
            current = await client.state(delivery.event_id)
            await self._authorize_audience(delivery, current.event.task_id)
            delivery.approval_id = None
            delivery.approval_text = ""
            if current.pending_actions:
                pending = current.pending_actions[0]
                delivery.approval_id = pending.id
                delivery.approval_text = f"{pending.kind} ({pending.risk_level})"
                if pending.id not in delivery.presented_approvals:
                    delivery.presented_approvals = [*delivery.presented_approvals[-31:], pending.id]
        await self.channel.update(track_id, self._render(delivery))
        delivery.cursor = cursor
        delivery.attempts = 0
        delivery.retry_at, delivery.lease_until, delivery.lease_owner = 0, 0, ""
        await self.host.write(
            row.key,
            StoreWrite(expected_revision=row.revision, value=delivery.model_dump(mode="json")),
        )

    async def _authorize_audience(self, delivery: Delivery, task_id: UUID | None) -> None:
        if delivery.group_id is None:
            if self.config.reply_mode != "sender_only":
                raise ValueError("Delivery mode changed; existing audience cannot be replaced")
            return
        if (
            self.config.reply_mode != "group_recipients"
            or self.config.group_recipients.get(delivery.group_id) != delivery.recipients
            or task_id is None
        ):
            raise ValueError("Group audience changed or task is unavailable")
        await self.channel.require_group_members(delivery.group_id, delivery.recipients)
        for staff in delivery.recipients:
            permission = await self.host.permissions(
                PermissionQuery(
                    automation_id=delivery.automation_id,
                    sender_id=f"{self.config.corp_id}:{staff}",
                    resource_kind="task",
                    resource_id=task_id,
                )
            )
            if "read" not in permission.actions:
                raise ValueError("Group recipient cannot read this task")

    def _render(self, delivery: Delivery) -> dict[str, str]:
        return CardTemplate.model_validate(delivery.template).render(
            title="OpsMesh",
            text=delivery.text,
            status=delivery.status,
            event_id=str(delivery.event_id),
            approval_id=str(delivery.approval_id) if delivery.approval_id else "",
            approval_text=delivery.approval_text,
        )


def _card_text(value: str) -> str:
    # Escaped emoji can occupy twelve bytes each in the platform's 64 KB JSON value limit.
    return value if len(value) <= 3000 else value[:3000] + "\n[output truncated]"
