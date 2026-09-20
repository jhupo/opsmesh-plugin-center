from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapabilityDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    kind: Literal["mcp_server", "skill", "message_trigger", "reply_channel"]
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    configuration_schema: dict[str, object] = Field(default_factory=dict)
    required_permissions: list[str] = Field(default_factory=list, max_length=32)


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = 1
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(min_length=1, max_length=160)
    execution: Literal["remote"] = "remote"
    capabilities: list[CapabilityDeclaration] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_capabilities(self) -> PluginManifest:
        keys = [item.key for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("Plugin capability keys must be unique")
        return self
