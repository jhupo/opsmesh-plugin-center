"""Data-only channel card mappings. Templates cannot execute code or grant actions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opsmesh_plugin_sdk.contracts import MessageAction


class CardAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    action: MessageAction

    @model_validator(mode="after")
    def control_only(self) -> "CardAction":
        if self.action not in {"pause", "resume", "cancel"}:
            raise ValueError("Card buttons support pause, resume and cancel only")
        return self


class CardTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1] = 1
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    channel: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    template_id: str = Field(min_length=1, max_length=240)
    parameters: dict[str, Literal["title", "text", "status", "event_id"]] = Field(
        min_length=1, max_length=32
    )
    actions: dict[str, CardAction] = Field(default_factory=dict, max_length=8)

    def render(self, *, title: str, text: str, status: str, event_id: str) -> dict[str, str]:
        values = {
            "title": title[:240],
            "text": text[:16000],
            "status": status[:80],
            "event_id": event_id,
        }
        return {parameter: values[source] for parameter, source in self.parameters.items()}
