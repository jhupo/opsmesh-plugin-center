from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from opsmesh_plugin_sdk.context import PluginContext, UserContext, UserIdentity


class PermissionQuery(UserContext):
    resource_kind: str = Field(min_length=1, max_length=40)
    resource_id: UUID


class PermissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[str]


class IdentityClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def context(self) -> PluginContext:
        response = await self._client.get(f"{self._path}/context")
        response.raise_for_status()
        return PluginContext.model_validate(response.json())

    async def resolve(self, context: UserContext) -> UserIdentity:
        response = await self._client.post(
            f"{self._path}/identity", json=context.model_dump(mode="json")
        )
        response.raise_for_status()
        return UserIdentity.model_validate(response.json())

    async def permissions(self, query: PermissionQuery) -> PermissionResult:
        response = await self._client.post(
            f"{self._path}/permissions", json=query.model_dump(mode="json")
        )
        response.raise_for_status()
        return PermissionResult.model_validate(response.json())
