"""Explicit user delegation; external attributes never constitute authorization."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    automation_id: UUID
    sender_id: str = Field(min_length=1, max_length=160)


class UserIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    display_name: str
    workspace_id: UUID


class PluginContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    install_id: UUID
    permissions: list[str]
