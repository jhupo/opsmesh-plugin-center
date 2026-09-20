"""Data-only extension declarations; installation never authorizes execution."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MessageAction = Literal["start", "follow_up", "add_instruction", "pause", "resume", "cancel"]
AttachmentKind = Literal["image", "file", "audio"]


class MessageAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: UUID
    kind: AttachmentKind
    filename: str = Field(min_length=1, max_length=260)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=1, le=20 * 1024 * 1024)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transcript: str = Field(default="", max_length=16000, repr=False)


class IncomingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    sender_id: str = Field(min_length=1, max_length=160)
    occurred_at: AwareDatetime
    text: str = Field(default="", max_length=16_000)
    contract_version: int = Field(default=1, ge=1)
    data: dict[str, object] = Field(default_factory=dict, max_length=64)
    action: MessageAction = "start"
    reply_to_event_id: UUID | None = None
    attachments: list[MessageAttachment] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_target(self) -> IncomingMessage:
        if (
            self.action in {"start", "follow_up", "add_instruction"}
            and not self.text
            and not self.data
            and not self.attachments
        ):
            raise ValueError("Message requires text or structured data")
        if self.attachments and self.action != "start":
            raise ValueError("Attachments belong to the initial message of a task")
        if len({item.file_id for item in self.attachments}) != len(self.attachments):
            raise ValueError("Attachment references must be unique")
        if (self.action == "start") != (self.reply_to_event_id is None):
            raise ValueError("Only start messages omit reply_to_event_id")
        if self.action in {"follow_up", "add_instruction"} and len(self.text) > 4000:
            raise ValueError("Follow-up instructions are limited to 4000 characters")
        return self


class AcceptedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    automation_id: UUID
    external_event_id: str
    conversation_id: str
    status: str
    task_id: UUID | None
    reply_delivery_id: UUID | None
    error_code: str | None


class PendingAction(BaseModel):
    id: UUID
    kind: str
    risk_level: str


class EventState(BaseModel):
    event: AcceptedEvent
    task_status: str | None
    output: dict[str, object]
    pending_actions: list[PendingAction]
    notification_sequence: int
    contract_version: int = 1
    output_error: str | None = None


class AutomationReply(BaseModel):
    sequence: int = Field(ge=1)
    automation_id: UUID
    event_id: UUID
    conversation_id: str
    source_event_id: str
    sender_id: str | None
    task_id: UUID
    status: str
    kind: Literal["result", "progress", "action_required", "control_applied"]
    output: dict[str, object]
    pending_actions: list[PendingAction] = Field(default_factory=list)
    contract_version: int = 1
    error_code: str | None = None


class AutomationDelivery(BaseModel):
    id: str
    type: Literal["automation.reply"]
    workspace_id: UUID
    delivery_attempt_id: UUID
    attempt: int = Field(ge=1)
    created_at: AwareDatetime
    data: AutomationReply


class AutomationStreamEvent(BaseModel):
    """NDJSON stream frame. Cursor is opaque; data never includes raw tool arguments/results."""

    event_id: UUID
    task_id: UUID | None
    kind: Literal[
        "state",
        "checkpoint",
        "stream.reset",
        "stream.reconnect",
        "stream.completed",
        "stream.revoked",
        "output.reset",
        "output.text",
        "output.completed",
        "output.rejected",
        "task.failed",
        "task.cancelled",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "tool.waiting",
        "approval.required",
    ]
    cursor: str
    run_id: UUID | None = None
    step_id: UUID | None = None
    attempt_id: UUID | None = None
    sequence: int | None = None
    data: dict[str, object] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_id: str = Field(min_length=1, max_length=160)
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    status: Literal["approved", "rejected"]


class AttachmentUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_id: str = Field(min_length=1, max_length=160)
    external_event_id: str = Field(min_length=1, max_length=160)
    slot: int = Field(ge=0, le=4)
    kind: AttachmentKind
    filename: str = Field(min_length=1, max_length=260)
    content_type: str = Field(min_length=1, max_length=120)
    transcript: str = Field(default="", max_length=16000, repr=False)
