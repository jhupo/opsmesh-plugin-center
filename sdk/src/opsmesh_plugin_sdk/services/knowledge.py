"""User-scoped knowledge retrieval and versioned semantic memory."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_plugin_sdk.context import UserContext


class KnowledgeQuery(UserContext):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)


class KnowledgeHit(BaseModel):
    id: UUID | None = None
    title: str
    snippet: str
    source_type: str
    source_id: UUID
    score: float


class MemoryWrite(UserContext):
    scope_type: Literal["workspace", "team", "agent"]
    scope_id: UUID
    memory_key: str = Field(min_length=1, max_length=160)
    knowledge_type: Literal["fact", "configuration", "policy", "procedure"]
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=100000)
    tags: list[str] = Field(default_factory=list, max_length=32)
    importance: int = Field(default=50, ge=0, le=100)
    expected_revision: int = Field(ge=0)


class MemoryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    revision: int
    title: str
    content: str


class KnowledgeClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def search(self, query: KnowledgeQuery) -> list[KnowledgeHit]:
        response = await self._client.post(
            f"{self._path}/knowledge/search", json=query.model_dump(mode="json")
        )
        response.raise_for_status()
        return [KnowledgeHit.model_validate(item) for item in response.json()]

    async def remember(self, request: MemoryWrite) -> MemoryReceipt:
        response = await self._client.post(
            f"{self._path}/memory", json=request.model_dump(mode="json")
        )
        response.raise_for_status()
        return MemoryReceipt.model_validate(response.json())
