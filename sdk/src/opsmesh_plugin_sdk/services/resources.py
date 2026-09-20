"""Authorized resource discovery. Results are not execution grants."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_plugin_sdk.context import UserContext

ResourceKind = Literal[
    "team",
    "agent",
    "project",
    "capability",
    "mcp_server",
    "mcp_tool",
    "skill",
    "workflow",
    "file",
    "knowledge",
    "memory",
    "automation",
]


class ResourceQuery(UserContext):
    resource_kind: ResourceKind
    action: Literal["read", "invoke"] = "read"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class ResourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    kind: ResourceKind
    name: str
    actions: list[str]


class ResourcePage(BaseModel):
    items: list[ResourceSummary]
    has_more: bool


class ResourcesClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def list(self, query: ResourceQuery) -> ResourcePage:
        response = await self._client.post(
            f"{self._path}/resources/query", json=query.model_dump(mode="json")
        )
        response.raise_for_status()
        return ResourcePage.model_validate(response.json())
