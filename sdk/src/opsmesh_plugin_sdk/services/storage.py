import re

import httpx
from pydantic import BaseModel, ConfigDict, Field


class StoredValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    revision: int
    value: dict[str, object]


class StoreWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    value: dict[str, object] = Field(max_length=128)


class StorageClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

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
