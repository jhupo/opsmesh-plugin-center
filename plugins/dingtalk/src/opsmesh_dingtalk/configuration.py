import os
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from opsmesh_plugin_sdk.cards import CardTemplate
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform_url: str
    workspace_id: UUID
    install_id: UUID
    platform_token: SecretStr
    client_id: str
    client_secret: SecretStr

    @model_validator(mode="after")
    def secure_endpoint(self) -> "Settings":
        url = urlsplit(self.platform_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not url.path.endswith("/api/v1/")
        ):
            raise ValueError("OPSMESH_URL must be an HTTPS API root ending /api/v1/")
        if not self.platform_token.get_secret_value().startswith("omp_"):
            raise ValueError("Use an installation-scoped plugin credential")
        return self

    @classmethod
    def environment(cls) -> "Settings":
        names = {
            "platform_url": "OPSMESH_URL",
            "workspace_id": "OPSMESH_WORKSPACE_ID",
            "install_id": "OPSMESH_INSTALL_ID",
            "platform_token": "OPSMESH_PLUGIN_TOKEN",
            "client_id": "DINGTALK_CLIENT_ID",
            "client_secret": "DINGTALK_CLIENT_SECRET",
        }
        return cls.model_validate({field: os.environ[name] for field, name in names.items()})


class ChannelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    automation_id: UUID
    corp_id: str = Field(min_length=1, max_length=120)
    contract_version: int = Field(default=1, ge=1)
    card: CardTemplate
    question_field: str = Field(default="question", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    user_field: str = Field(default="user", pattern=r"^[a-z][a-z0-9_]{0,63}$")
    reply_mode: Literal["sender_only"] = "sender_only"
    poll_seconds: int = Field(default=3, ge=2, le=30)
    retention_hours: int = Field(default=24, ge=1, le=168)

    @model_validator(mode="after")
    def channel(self) -> "ChannelConfiguration":
        if self.card.channel != "dingtalk" or self.question_field == self.user_field:
            raise ValueError("Invalid DingTalk input/card mapping")
        return self
