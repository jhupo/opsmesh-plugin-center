"""Data-only channel card mappings. Templates cannot execute code or grant actions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CardAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    action: Literal["pause", "resume", "cancel", "approve", "reject"]


class CardTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1] = 1
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    channel: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    template_id: str = Field(min_length=1, max_length=240)
    parameters: dict[
        str, Literal["title", "text", "status", "event_id", "approval_id", "approval_text"]
    ] = Field(min_length=1, max_length=32)
    actions: dict[str, CardAction] = Field(default_factory=dict, max_length=8)

    def render(
        self,
        *,
        title: str,
        text: str,
        status: str,
        event_id: str,
        approval_id: str = "",
        approval_text: str = "",
    ) -> dict[str, str]:
        values = {
            "title": title[:240],
            "text": text[:16000],
            "status": status[:80],
            "event_id": event_id,
            "approval_id": approval_id,
            "approval_text": approval_text[:1000],
        }
        return {parameter: values[source] for parameter, source in self.parameters.items()}
