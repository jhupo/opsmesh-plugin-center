"""Installation-scoped platform services. Never exposes database or host access."""

import re
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_plugin_sdk.client import AsyncAutomationClient


class StoredValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    revision: int
    value: dict[str, object]


class StoreWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    value: dict[str, object] = Field(max_length=128)


class PluginLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["info", "warning", "error"] = "info"
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    event_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict, max_length=32)


class PermissionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    automation_id: UUID
    sender_id: str = Field(min_length=1, max_length=160)
    resource_kind: str = Field(min_length=1, max_length=40)
    resource_id: UUID


class PermissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[str]


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_id: str = Field(min_length=1, max_length=160)
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    status: Literal["approved", "rejected"]


class PluginServicesClient:
    """Caller owns the HTTPX client, authentication, lifecycle and retry policy."""

    def __init__(self, client: httpx.AsyncClient, workspace_id: UUID, install_id: UUID) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._install_id = install_id
        self._path = f"plugin-runtime/{workspace_id}/{install_id}"

    def automation(self, automation_id: UUID) -> AsyncAutomationClient:
        return AsyncAutomationClient(
            self._client,
            self._workspace_id,
            automation_id,
            install_id=self._install_id,
        )

    async def configuration(self) -> dict[str, object]:
        response = await self._client.get(f"{self._path}/configuration")
        response.raise_for_status()
        return dict(response.json())

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

    async def read(self, key: str) -> StoredValue | None:
        self._validate_key(key)
        response = await self._client.get(f"{self._path}/storage/{key}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return StoredValue.model_validate(response.json())

    async def write(self, key: str, value: StoreWrite) -> StoredValue:
        self._validate_key(key)
        response = await self._client.put(
            f"{self._path}/storage/{key}", json=value.model_dump(mode="json")
        )
        response.raise_for_status()
        return StoredValue.model_validate(response.json())

    async def log(self, entry: PluginLog) -> None:
        response = await self._client.post(f"{self._path}/logs", json=entry.model_dump(mode="json"))
        response.raise_for_status()

    async def permissions(self, query: PermissionQuery) -> PermissionResult:
        response = await self._client.post(
            f"{self._path}/permissions", json=query.model_dump(mode="json")
        )
        response.raise_for_status()
        return PermissionResult.model_validate(response.json())

    async def values(self, *, prefix: str = "", offset: int = 0) -> list[StoredValue]:
        response = await self._client.get(
            f"{self._path}/storage", params={"prefix": prefix, "offset": offset}
        )
        response.raise_for_status()
        return [StoredValue.model_validate(value) for value in response.json()]

    async def delete(self, key: str, *, expected_revision: int) -> None:
        self._validate_key(key)
        response = await self._client.delete(
            f"{self._path}/storage/{key}", params={"expected_revision": expected_revision}
        )
        response.raise_for_status()

    @staticmethod
    def _validate_key(key: str) -> None:
        if key in {".", ".."} or re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", key) is None:
            raise ValueError("Invalid plugin storage key")
