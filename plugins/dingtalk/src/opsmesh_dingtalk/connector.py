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
from opsmesh_plugin_sdk.services import PluginLog, PluginServicesClient, StoredValue, StoreWrite
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_dingtalk.channel import ChannelMessage
from opsmesh_dingtalk.configuration import ChannelConfiguration


class CardChannel(Protocol):
    async def create(
        self, track_id: str, staff_id: str, config: ChannelConfiguration, values: dict[str, str]
    ) -> None: ...
    async def update(self, track_id: str, values: dict[str, str]) -> None: ...


class Delivery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: IncomingMessage
    staff_id: str
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
        accepted = await self.host.automation(self.config.automation_id).submit(message)
        key = self.key(message)
        current = await self.host.read(key)
        if current is None:
            delivery = Delivery(
                message=message,
                staff_id=incoming.staff_id,
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
        self, track_id: str, sender_id: str, action_id: str, callback_id: str, occurred_at: datetime
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
        action = self.config.card.actions[action_id].action
        original = CardTemplate.model_validate(delivery.template).actions.get(action_id)
        if original is None or original.action != action:
            raise ValueError("Card action configuration changed")
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
        await client.state(delivery.event_id)
        track_id = "opsmesh_" + row.key[5:]
        if not delivery.created:
            snapshot_config = self.config.model_copy(
                update={"card": CardTemplate.model_validate(delivery.template)}
            )
            await self.channel.create(
                track_id, delivery.staff_id, snapshot_config, self._render(delivery)
            )
            delivery.created = True
        cursor = delivery.cursor
        async for frame in client.events(delivery.event_id, cursor=cursor, once=True):
            cursor = frame.cursor
            if frame.kind == "stream.revoked":
                delivery.blocked = True
                delivery.status, delivery.text = "access_revoked", ""
                break
            if frame.kind in {"stream.reset", "output.reset"}:
                delivery.text = ""
            elif frame.kind == "output.text":
                delivery.text = str(frame.data.get("text", ""))[:8000]
                delivery.status = "working"
            elif frame.kind.startswith("tool."):
                delivery.status = frame.kind + ":" + str(frame.data.get("name", ""))[:40]
            elif frame.kind == "approval.required":
                delivery.status = "approval_required_in_opsmesh"
            elif frame.kind == "output.completed":
                delivery.text = json.dumps(frame.data.get("output", {}), ensure_ascii=False)[:8000]
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
            await client.state(delivery.event_id)
        await self.channel.update(track_id, self._render(delivery))
        delivery.cursor = cursor
        delivery.attempts = 0
        delivery.retry_at, delivery.lease_until, delivery.lease_owner = 0, 0, ""
        await self.host.write(
            row.key,
            StoreWrite(expected_revision=row.revision, value=delivery.model_dump(mode="json")),
        )

    def _render(self, delivery: Delivery) -> dict[str, str]:
        return CardTemplate.model_validate(delivery.template).render(
            title="OpsMesh",
            text=delivery.text,
            status=delivery.status,
            event_id=str(delivery.event_id),
        )
