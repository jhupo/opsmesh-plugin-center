"""Official DingTalk SDK boundary; no platform policy or hand-written HTTP protocol."""

import json
import logging
import mimetypes
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import dingtalk_stream
import httpx
from alibabacloud_dingtalk.card_1_0 import models as cards
from alibabacloud_dingtalk.card_1_0.client import Client
from alibabacloud_dingtalk.im_1_0 import models as groups
from alibabacloud_dingtalk.im_1_0.client import Client as GroupClient
from alibabacloud_dingtalk.oauth2_1_0.client import Client as OAuthClient
from alibabacloud_dingtalk.oauth2_1_0.models import GetAccessTokenRequest
from alibabacloud_dingtalk.robot_1_0 import models as robot
from alibabacloud_dingtalk.robot_1_0.client import Client as RobotClient
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions
from opsmesh_plugin_sdk.contracts import AttachmentKind, IncomingMessage

from opsmesh_dingtalk.configuration import ChannelConfiguration


@dataclass(frozen=True)
class ChannelMessage:
    message: IncomingMessage
    staff_id: str
    group_id: str | None
    attachments: tuple["RawAttachment", ...] = ()


@dataclass(frozen=True)
class RawAttachment:
    download_code: str
    kind: AttachmentKind
    filename: str
    content_type: str
    text: str = ""


def parse_message(data: dict[str, Any], config: ChannelConfiguration) -> ChannelMessage:
    incoming = dingtalk_stream.ChatbotMessage.from_dict(data)
    if (
        incoming.sender_corp_id != config.corp_id
        or not incoming.sender_staff_id
        or incoming.message_type not in {"text", "picture", "richText", "file", "audio"}
        or not incoming.message_id
        or not incoming.conversation_id
        or not data.get("createAt")
    ):
        raise ValueError("Unsupported message or unverified enterprise sender")
    raw_content = data.get("content", {})
    if isinstance(raw_content, str):
        try:
            raw_content = json.loads(raw_content)
        except json.JSONDecodeError:
            raise ValueError("Invalid DingTalk media content") from None
    if not isinstance(raw_content, dict):
        raise ValueError("Invalid DingTalk media content")
    attachments: list[RawAttachment] = []
    text = str(incoming.text.content).strip() if incoming.message_type == "text" else ""
    if incoming.message_type == "picture":
        code = getattr(incoming.image_content, "download_code", None)
        if code:
            attachments.append(
                RawAttachment(
                    str(code), "image", "image.jpg", "image/jpeg"
                )
            )
    elif incoming.message_type == "audio":
        code = raw_content.get("downloadCode")
        recognition = str(raw_content.get("recognition") or "").strip()
        text = recognition
        if code:
            attachments.append(
                RawAttachment(
                    str(code),
                    "audio",
                    "voice.amr",
                    "audio/amr",
                    recognition,
                )
            )
    elif incoming.message_type == "file":
        code = raw_content.get("downloadCode")
        if code:
            filename = str(raw_content.get("fileName") or "attachment.bin")[:260]
            attachments.append(
                RawAttachment(
                    str(code), "file", filename, "application/octet-stream"
                )
            )
    elif incoming.message_type == "richText":
        for item in getattr(incoming.rich_text_content, "rich_text_list", []) or []:
            code = item.get("downloadCode") or item.get("pictureDownloadCode")
            if code:
                attachments.append(
                    RawAttachment(
                        str(code),
                        "image",
                        "image.jpg",
                        "image/jpeg",
                    )
                )
            if isinstance(item.get("text"), str):
                text += item["text"]
    if len(attachments) > 5:
        raise ValueError("At most five attachments are allowed")
    if any(item.kind not in config.allowed_attachment_kinds for item in attachments):
        raise ValueError("Attachment kind is not enabled")
    if incoming.message_type == "audio" and not text:
        raise ValueError("DingTalk voice recognition is required for audio messages")
    if not text and not attachments:
        raise ValueError("Message has no supported content")
    staff_id = str(incoming.sender_staff_id)
    sender_id = f"{config.corp_id}:{staff_id}"
    # Partition group conversations by sender: the group is never a shared authorization scope.
    conversation = str(incoming.conversation_id)
    import hashlib

    conversation_id = hashlib.sha256(f"{conversation}:{sender_id}".encode()).hexdigest()
    return ChannelMessage(
        IncomingMessage(
            event_id=str(incoming.message_id),
            conversation_id=conversation_id,
            sender_id=sender_id,
            occurred_at=datetime.fromtimestamp(int(data["createAt"]) / 1000, UTC),
            contract_version=config.contract_version,
            data={
                config.question_field: text,
                config.user_field: {"id": sender_id, "name": str(incoming.sender_nick)},
            },
        ),
        staff_id,
        conversation if incoming.conversation_type == "2" else None,
        tuple(attachments),
    )


def parse_callback(
    data: dict[str, Any], config: ChannelConfiguration
) -> tuple[str, str, str, UUID | None]:
    incoming = dingtalk_stream.CardCallbackMessage.from_dict(data)
    if incoming.corp_id != config.corp_id or not incoming.user_id or not incoming.card_instance_id:
        raise ValueError("Unverified card sender")
    private = incoming.content.get("cardPrivateData", {})
    action = private.get("params", {}).get("action")
    if not isinstance(action, str) or action not in config.card.actions:
        raise ValueError("Unsupported card action")
    approval_id = None
    if config.card.actions[action].action in {"approve", "reject"}:
        approval_id = UUID(str(private.get("params", {}).get("approval_id", "")))
    return (
        str(incoming.card_instance_id),
        f"{config.corp_id}:{incoming.user_id}",
        action,
        approval_id,
    )


class DingTalkCards:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = ""
        self.expires_at = 0.0
        self.oauth = OAuthClient(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.client = Client(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.groups = GroupClient(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.robot = RobotClient(
            Config(protocol="https", region_id="central", endpoint="api.dingtalk.com")
        )
        self.options = RuntimeOptions(
            read_timeout=15000, connect_timeout=5000, autoretry=True, max_attempts=3
        )

    async def create(
        self,
        track_id: str,
        staff_id: str,
        config: ChannelConfiguration,
        values: dict[str, str],
        *,
        group_id: str | None,
        recipients: list[str],
    ) -> None:
        async with self.authorization() as token:
            # Always deliver to the requesting employee's robot conversation, including group input.
            # out_track_id is stable across crashes/retries and used by DingTalk for idempotency.
            request = cards.CreateAndDeliverRequest(
                out_track_id=track_id,
                card_template_id=config.card.template_id,
                card_data=cards.CreateAndDeliverRequestCardData(card_param_map=values),
                callback_type="STREAM",
                user_id_type=1,
                open_space_id=f"dtv1.card//IM_ROBOT.{staff_id}",
                im_robot_open_deliver_model=cards.CreateAndDeliverRequestImRobotOpenDeliverModel(
                    space_type="IM_ROBOT",
                    robot_code=self.client_id,
                ),
                im_robot_open_space_model=cards.CreateAndDeliverRequestImRobotOpenSpaceModel(
                    support_forward=False,
                ),
            )
            if group_id is not None:
                request.open_space_id = f"dtv1.card//IM_GROUP.{group_id}"
                request.im_robot_open_deliver_model = None
                request.im_robot_open_space_model = None
                request.im_group_open_deliver_model = (
                    cards.CreateAndDeliverRequestImGroupOpenDeliverModel(
                        robot_code=self.client_id,
                        recipients=recipients,
                    )
                )
                request.im_group_open_space_model = (
                    cards.CreateAndDeliverRequestImGroupOpenSpaceModel(support_forward=False)
                )
            await self.client.create_and_deliver_with_options_async(
                request,
                cards.CreateAndDeliverHeaders(x_acs_dingtalk_access_token=token),
                self.options,
            )

    async def require_group_members(self, group_id: str, recipients: list[str]) -> None:
        async with self.authorization() as token:
            for staff_id in recipients:
                result = await self.groups.check_user_is_group_member_with_options_async(
                    groups.CheckUserIsGroupMemberRequest(
                        open_conversation_id=group_id,
                        user_id=staff_id,
                    ),
                    groups.CheckUserIsGroupMemberHeaders(x_acs_dingtalk_access_token=token),
                    self.options,
                )
                if result.body.result is not True:
                    raise ValueError("Group recipient is no longer a member")

    async def download(self, attachment: RawAttachment) -> tuple[bytes, str]:
        async with self.authorization() as token:
            response = await self.robot.robot_message_file_download_with_options_async(
                robot.RobotMessageFileDownloadRequest(
                    download_code=attachment.download_code, robot_code=self.client_id
                ),
                robot.RobotMessageFileDownloadHeaders(x_acs_dingtalk_access_token=token),
                self.options,
            )
            url = str(response.body.download_url or "") if response.body else ""
            parsed = urlsplit(url or "")
            host = parsed.hostname or ""
            if (
                parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in {None, 443}
                or not any(
                    host == domain or host.endswith("." + domain)
                    for domain in ("dingtalk.com", "alicdn.com", "aliyuncs.com")
                )
            ):
                raise ValueError("DingTalk returned an invalid attachment URL")
        async with (
            httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False,
            ) as http,
            http.stream("GET", url) as result,
        ):
            result.raise_for_status()
            content_type = result.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type == "application/octet-stream" or not content_type:
                content_type = (
                    mimetypes.guess_type(attachment.filename)[0] or "application/octet-stream"
                )
            content = bytearray()
            async for chunk in result.aiter_bytes():
                content.extend(chunk)
                if len(content) > 20 * 1024 * 1024:
                    raise ValueError("DingTalk attachment exceeds limit")
            return bytes(content), content_type

    async def update(self, track_id: str, values: dict[str, str]) -> None:
        async with self.authorization() as token:
            await self.client.update_card_with_options_async(
                cards.UpdateCardRequest(
                    out_track_id=track_id,
                    card_data=cards.UpdateCardRequestCardData(card_param_map=values),
                ),
                cards.UpdateCardHeaders(x_acs_dingtalk_access_token=token),
                self.options,
            )

    @asynccontextmanager
    async def authorization(self) -> AsyncIterator[str]:
        token = await self.access_token()
        try:
            yield token
        except Exception:
            # A revoked/expired channel token must be refreshed before durable retry.
            self.expires_at = 0
            raise

    async def access_token(self) -> str:
        if self.token and time.monotonic() < self.expires_at:
            return self.token
        response = await self.oauth.get_access_token_with_options_async(
            GetAccessTokenRequest(app_key=self.client_id, app_secret=self.client_secret),
            {},
            self.options,
        )
        if not response.body.access_token or not response.body.expire_in:
            raise RuntimeError("DingTalk token unavailable")
        self.token = str(response.body.access_token)
        self.expires_at = time.monotonic() + max(0, int(response.body.expire_in) - 300)
        return self.token


class SDKLogFilter(logging.Filter):
    """Upstream logs can include credential responses and message bodies; keep codes only."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "dingtalk.sdk_event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True
