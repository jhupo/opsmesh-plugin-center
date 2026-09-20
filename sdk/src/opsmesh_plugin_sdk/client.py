"""Composed plugin client. The caller owns HTTPX authentication and lifetime."""

from uuid import UUID

import httpx

from opsmesh_plugin_sdk.messaging.client import AsyncAutomationClient, MessageServicesClient
from opsmesh_plugin_sdk.services.configuration import ConfigurationClient
from opsmesh_plugin_sdk.services.identity import IdentityClient
from opsmesh_plugin_sdk.services.knowledge import KnowledgeClient
from opsmesh_plugin_sdk.services.observability import ObservabilityClient
from opsmesh_plugin_sdk.services.resources import ResourcesClient
from opsmesh_plugin_sdk.services.storage import StorageClient


class PluginClient:
    def __init__(self, client: httpx.AsyncClient, workspace_id: UUID, install_id: UUID) -> None:
        self._http = client
        self.workspace_id = workspace_id
        self.install_id = install_id
        path = f"plugin-runtime/{workspace_id}/{install_id}"
        self.configuration = ConfigurationClient(client, path)
        self.identity = IdentityClient(client, path)
        self.storage = StorageClient(client, path)
        self.observability = ObservabilityClient(client, path)
        self.messages = MessageServicesClient(client, path)
        self.resources = ResourcesClient(client, path)
        self.knowledge = KnowledgeClient(client, path)

    def automation(self, automation_id: UUID) -> AsyncAutomationClient:
        return AsyncAutomationClient(
            self._http, self.workspace_id, automation_id, install_id=self.install_id
        )
