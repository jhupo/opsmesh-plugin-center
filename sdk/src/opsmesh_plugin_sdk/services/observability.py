from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field


class PluginLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["info", "warning", "error"] = "info"
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    event_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict, max_length=32)


class ObservabilityClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def log(self, entry: PluginLog) -> None:
        response = await self._client.post(f"{self._path}/logs", json=entry.model_dump(mode="json"))
        response.raise_for_status()
