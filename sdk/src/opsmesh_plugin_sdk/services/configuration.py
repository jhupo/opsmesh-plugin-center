import httpx


class ConfigurationClient:
    def __init__(self, client: httpx.AsyncClient, path: str) -> None:
        self._client = client
        self._path = path

    async def read(self) -> dict[str, object]:
        response = await self._client.get(f"{self._path}/configuration")
        response.raise_for_status()
        return dict(response.json())
