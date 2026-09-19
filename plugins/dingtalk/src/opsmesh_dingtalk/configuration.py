import json
import os
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from opsmesh_plugin_sdk.cards import CardTemplate
from opsmesh_plugin_sdk.contracts import AttachmentKind
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
    allowed_attachment_kinds: list[AttachmentKind] = Field(default_factory=list, max_length=3)
    reply_mode: Literal["sender_only", "group_recipients"] = "sender_only"
    group_recipients: dict[str, list[str]] = Field(default_factory=dict, max_length=64)
    poll_seconds: int = Field(default=3, ge=2, le=30)
    retention_hours: int = Field(default=24, ge=1, le=168)

    @model_validator(mode="after")
    def channel(self) -> "ChannelConfiguration":
        if self.card.channel != "dingtalk" or self.question_field == self.user_field:
            raise ValueError("Invalid DingTalk input/card mapping")
        if len(json.dumps(self.card.model_dump(mode="json"), ensure_ascii=True)) > 8000:
            raise ValueError("Card mapping exceeds the durable delivery budget")
        if self.reply_mode == "group_recipients" and not self.group_recipients:
            raise ValueError("Group replies require explicit group and staff recipients")
        for group, recipients in self.group_recipients.items():
            if len(json.dumps(recipients, ensure_ascii=True)) > 8000:
                raise ValueError("Group audience exceeds the durable delivery budget")
            if not group or len(group) > 256 or not 1 <= len(recipients) <= 20:
                raise ValueError("Invalid group recipient configuration")
            if len(set(recipients)) != len(recipients) or any(
                not staff or len(staff) > 120 or ":" in staff for staff in recipients
            ):
                raise ValueError("Group recipients must be unique enterprise staff IDs")
        return self
