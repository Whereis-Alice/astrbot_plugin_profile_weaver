from __future__ import annotations

from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

from llm_tools import (
    FORGET_TOOL_NAME,
    REMEMBER_TOOL_NAME,
    VIEW_TOOL_NAME,
    ProfileWeaverForgetTool,
    ProfileWeaverRememberTool,
    ProfileWeaverViewTool,
)
from profile_store import AuditActor, DEFAULT_FIELDS, ProfileStore

DEFAULT_PROFILE_PROMPT_TEMPLATE = """<ProfileWeaver>
当前说话人：{sender_name} ({sender_id})
画像作用域：{session_scope}

当前画像：
{profile_summary}

基础字段：
{field_catalog}

当前自定义字段：
{custom_field_catalog}

规则：
1. 这些画像只属于当前消息发送者，不属于你自己，也不属于别的群友。
2. 只有当前发送者明确谈论自己、表达稳定偏好、或纠正自己的信息时，才允许调用画像写入工具。
3. 当前消息提到其他人、转述他人、开玩笑、角色扮演、引用历史聊天、或信息不确定时，不要写入画像。
4. 优先复用已有字段；确实不够表达时，才允许创建当前用户专属自定义字段。
5. 临时状态、推测、系统设定、消息过程信息不要存入画像。
6. 删除画像前，必须确认用户明确要求删除或纠正。

可用工具：{tool_names}
</ProfileWeaver>"""

REMEMBER_SOURCE_KINDS = {"self_report", "self_preference", "self_correction"}
FORGET_SOURCE_KINDS = {"self_request", "self_correction"}
FIRST_PERSON_MARKERS = (
    "我",
    "我的",
    "我是",
    "我叫",
    "本人",
    "俺",
    "咱",
    "自己",
    "纠正一下",
    "更正一下",
)
THIRD_PARTY_MARKERS = (
    "@",
    "他",
    "她",
    "ta",
    "TA",
    "他们",
    "她们",
    "别人",
    "群友",
    "朋友说",
    "他说",
    "她说",
)


@register(
    "ProfileWeaver",
    "Whereis-Alice",
    "更安全的用户画像记忆插件，使用 LLM 工具替代隐藏标签写入，并为每位用户支持自定义画像字段。",
    "2.0.0",
)
class ProfileWeaverPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        data_dir = StarTools.get_data_dir()
        default_fields = self.config.get("default_fields") or self.config.get("allowed_fields") or [
            name for name, _ in DEFAULT_FIELDS
        ]
        self.store = ProfileStore(
            data_dir=data_dir,
            builtin_fields=default_fields,
            max_notes_count=self.config.get("max_notes_count", 5),
            custom_field_name_max_length=self.config.get("custom_field_name_max_length", 16),
            field_value_max_length=self.config.get("field_value_max_length", 160),
        )
        self.context.add_llm_tools(
            ProfileWeaverViewTool(plugin=self, active=self._llm_tools_enabled()),
            ProfileWeaverRememberTool(plugin=self, active=self._llm_tools_enabled()),
            ProfileWeaverForgetTool(plugin=self, active=self._llm_tools_enabled()),
        )

    @property
    def session_based(self) -> bool:
        return bool(self.config.get("session_based", False))

    def _llm_tools_enabled(self) -> bool:
        return bool(self.config.get("llm_tools_enabled", True))

    def _allow_llm_custom_fields(self) -> bool:
        return bool(self.config.get("allow_llm_custom_fields", True))

    def _allow_user_custom_fields(self) -> bool:
        return bool(self.config.get("allow_user_custom_fields", True))

    def _strict_identity_guard(self) -> bool:
        return bool(self.config.get("strict_identity_guard", True))

    def _debug_enabled(self) -> bool:
        return str(self.config.get("debug_log_level", "INFO")).upper() == "DEBUG"

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            logger.debug(f"[ProfileWeaver] {message}")

    def _get_session_id(self, event: AstrMessageEvent) -> str | None:
        return event.unified_msg_origin if self.session_based else None

    def _build_actor(self, event: AstrMessageEvent, actor_type: str) -> AuditActor:
        return AuditActor(
            actor_type=actor_type,
            actor_id=str(event.get_sender_id()),
            actor_name=str(event.get_sender_name()),
        )

    def _is_group_chat(self, event: AstrMessageEvent) -> bool:
        origin = str(event.unified_msg_origin or "")
        return "group" in origin.lower()

    def _is_ambiguous_identity(self, message_text: str, evidence: str) -> bool:
        if not self._strict_identity_guard():
            return False
        merged_text = f"{message_text}\n{evidence}".lower()
        mentions_third_party = any(marker.lower() in merged_text for marker in THIRD_PARTY_MARKERS)
        mentions_self = any(marker in f"{message_text}{evidence}" for marker in FIRST_PERSON_MARKERS)
        return mentions_third_party and not mentions_self

    def _build_prompt(self, event: AstrMessageEvent) -> str:
        sender_id = str(event.get_sender_id())
        sender_name = str(event.get_sender_name())
        session_id = self._get_session_id(event)
        profile_summary = self.store.format_profile_summary(sender_id, session_id)
        field_catalog = self.store.format_field_catalog(sender_id, session_id)
        custom_field_catalog = self.store.format_custom_field_catalog(sender_id, session_id)
        prompt_template = self.config.get("profile_prompt_template") or self.config.get("profile_prompt") or DEFAULT_PROFILE_PROMPT_TEMPLATE
        return prompt_template.format(
            sender_id=sender_id,
            sender_name=sender_name,
            session_scope="当前会话隔离" if self.session_based else "全局共享",
            profile_summary=profile_summary,
            field_catalog=field_catalog,
            custom_field_catalog=custom_field_catalog,
            tool_names=", ".join([VIEW_TOOL_NAME, REMEMBER_TOOL_NAME, FORGET_TOOL_NAME]),
        )

    def _validate_evidence(
        self,
        event: AstrMessageEvent,
        evidence: str,
        allowed_source_kinds: set[str],
        source_kind: str,
    ) -> str | None:
        message_text = str(event.message_str or "").strip()
        evidence_text = str(evidence or "").strip()
        if source_kind not in allowed_source_kinds:
            return "拒绝执行：source_kind 不在允许范围内。"
        if not message_text:
            return "拒绝执行：当前消息为空，无法校验画像依据。"
        if not evidence_text:
            return "拒绝执行：evidence 不能为空。"
        if evidence_text not in message_text:
            return "拒绝执行：evidence 必须直接来自当前用户本轮消息。"
        if self._is_ambiguous_identity(message_text, evidence_text):
            return "拒绝执行：当前消息同时提到其他人且缺少明确自述，容易写错对象。请先澄清，再决定是否记录。"
        return None

    def _ensure_known_or_creatable_field(
        self,
        *,
        user_id: str,
        session_id: str | None,
        field_name: str,
        create_custom_field: bool,
        allow_custom_field: bool,
    ) -> str | None:
        if self.store.is_known_field(user_id, field_name, session_id):
            return None
        if create_custom_field and allow_custom_field:
            return None
        return "拒绝执行：字段不存在。请优先使用已有字段；如果确实需要新字段，请明确允许创建自定义字段。"

    async def handle_llm_view(self, event: AstrMessageEvent) -> str:
        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        summary = self.store.format_profile_summary(user_id, session_id)
        fields = self.store.format_field_catalog(user_id, session_id)
        custom_fields = self.store.format_custom_field_catalog(user_id, session_id)
        return (
            f"当前用户画像摘要：\n{summary}\n\n"
            f"可用字段：\n{fields}\n\n"
            f"当前自定义字段：\n{custom_fields}\n\n"
            "删除备注项时，可把字段写成 备注:序号，例如 备注:2。"
        )

    async def handle_llm_remember(
        self,
        event: AstrMessageEvent,
        **kwargs: Any,
    ) -> str:
        if not self._llm_tools_enabled():
            return "画像工具当前已关闭。"
        field_name = str(kwargs.get("field_name") or "").strip()
        value = str(kwargs.get("value") or "").strip()
        evidence = str(kwargs.get("evidence") or "").strip()
        source_kind = str(kwargs.get("source_kind") or "").strip()
        create_custom_field = bool(kwargs.get("create_custom_field", False))
        field_description = str(kwargs.get("field_description") or "").strip()

        validation_error = self._validate_evidence(event, evidence, REMEMBER_SOURCE_KINDS, source_kind)
        if validation_error:
            return validation_error

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        field_error = self._ensure_known_or_creatable_field(
            user_id=user_id,
            session_id=session_id,
            field_name=field_name,
            create_custom_field=create_custom_field,
            allow_custom_field=self._allow_llm_custom_fields(),
        )
        if field_error:
            return field_error

        result = self.store.upsert_field(
            user_id=user_id,
            subject_name=str(event.get_sender_name()),
            field_name=field_name,
            value=value,
            session_id=session_id,
            actor=self._build_actor(event, "llm_tool"),
            source_kind=source_kind,
            evidence=evidence,
            allow_custom_field=self._allow_llm_custom_fields() and create_custom_field,
            field_description=field_description,
        )
        self._debug(f"LLM remember result for {user_id}: {result.message}")
        return result.message

    async def handle_llm_forget(
        self,
        event: AstrMessageEvent,
        **kwargs: Any,
    ) -> str:
        if not self._llm_tools_enabled():
            return "画像工具当前已关闭。"
        field_selector = str(kwargs.get("field_selector") or "").strip()
        evidence = str(kwargs.get("evidence") or "").strip()
        source_kind = str(kwargs.get("source_kind") or "").strip()
        validation_error = self._validate_evidence(event, evidence, FORGET_SOURCE_KINDS, source_kind)
        if validation_error:
            return validation_error

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        result = self.store.delete_field(
            user_id=user_id,
            session_id=session_id,
            field_selector=field_selector,
            actor=self._build_actor(event, "llm_tool"),
            source_kind=source_kind,
            evidence=evidence,
        )
        self._debug(f"LLM forget result for {user_id}: {result.message}")
        return result.message

    @filter.on_llm_request()
    async def inject_profile_context(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        prompt = self._build_prompt(event)
        current_system_prompt = str(req.system_prompt or "").rstrip()
        req.system_prompt = f"{current_system_prompt}\n\n{prompt}".strip()

    @filter.command("我的画像")
    async def show_my_profile(self, event: AstrMessageEvent) -> None:
        if self._is_group_chat(event) and not bool(self.config.get("allow_profile_in_group", False)):
            denied_msg = self.config.get(
                "group_profile_denied_msg",
                "画像内容可能涉及隐私，请私聊查看。",
            )
            yield event.plain_result(str(denied_msg))
            return

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        summary = self.store.format_profile_summary(user_id, session_id)
        if summary == "暂无记录":
            yield event.plain_result("暂时还没有你的画像记录。")
            return

        last_updated = self.store.get_last_updated(user_id, session_id) or "未知"
        yield event.plain_result(f"你的画像：\n{summary}\n\n最后更新：{last_updated}")

    @filter.command("画像字段")
    async def show_field_catalog(self, event: AstrMessageEvent) -> None:
        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        catalog = self.store.format_field_catalog(user_id, session_id)
        yield event.plain_result(f"可用画像字段：\n{catalog}")

    @filter.command("设置画像")
    async def set_my_profile(self, event: AstrMessageEvent, field_name: str, value: str) -> None:
        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        allow_custom_field = self._allow_user_custom_fields()
        result = self.store.upsert_field(
            user_id=user_id,
            subject_name=str(event.get_sender_name()),
            field_name=field_name,
            value=value,
            session_id=session_id,
            actor=self._build_actor(event, "user_command"),
            source_kind="manual_edit",
            evidence=str(event.message_str or ""),
            allow_custom_field=allow_custom_field,
            field_description="用户通过命令手动创建的自定义字段",
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.command("删除画像")
    async def delete_my_profile(self, event: AstrMessageEvent, field_selector: str) -> None:
        result = self.store.delete_field(
            user_id=str(event.get_sender_id()),
            session_id=self._get_session_id(event),
            field_selector=field_selector,
            actor=self._build_actor(event, "user_command"),
            source_kind="manual_delete",
            evidence=str(event.message_str or ""),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.command("清空画像")
    async def clear_my_profile(self, event: AstrMessageEvent) -> None:
        result = self.store.clear_profile(
            user_id=str(event.get_sender_id()),
            session_id=self._get_session_id(event),
            actor=self._build_actor(event, "user_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查询画像")
    async def admin_query_profile(self, event: AstrMessageEvent, user_id: str) -> None:
        target_user_id = str(user_id).strip()
        session_id = self._get_session_id(event)
        summary = self.store.format_profile_summary(target_user_id, session_id)
        if summary == "暂无记录":
            yield event.plain_result(f"用户 {target_user_id} 没有画像记录。")
            return
        last_updated = self.store.get_last_updated(target_user_id, session_id) or "未知"
        yield event.plain_result(
            f"用户 {target_user_id} 的画像：\n{summary}\n\n最后更新：{last_updated}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("修改画像")
    async def admin_set_profile(
        self,
        event: AstrMessageEvent,
        user_id: str,
        field_name: str,
        value: str,
    ) -> None:
        target_user_id = str(user_id).strip()
        session_id = self._get_session_id(event)
        old_profile = self.store.get_profile(target_user_id, session_id)
        subject_name = str(old_profile.get("subject_name") or target_user_id)
        result = self.store.upsert_field(
            user_id=target_user_id,
            subject_name=subject_name,
            field_name=field_name,
            value=value,
            session_id=session_id,
            actor=self._build_actor(event, "admin_command"),
            source_kind="admin_edit",
            evidence=str(event.message_str or ""),
            allow_custom_field=True,
            field_description="管理员通过命令创建的自定义字段",
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除画像字段")
    async def admin_delete_profile_field(
        self,
        event: AstrMessageEvent,
        user_id: str,
        field_selector: str,
    ) -> None:
        result = self.store.delete_field(
            user_id=str(user_id).strip(),
            session_id=self._get_session_id(event),
            field_selector=field_selector,
            actor=self._build_actor(event, "admin_command"),
            source_kind="admin_delete",
            evidence=str(event.message_str or ""),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("清空用户画像")
    async def admin_clear_profile(self, event: AstrMessageEvent, user_id: str) -> None:
        result = self.store.clear_profile(
            user_id=str(user_id).strip(),
            session_id=self._get_session_id(event),
            actor=self._build_actor(event, "admin_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像审计")
    async def admin_audit_profile(
        self,
        event: AstrMessageEvent,
        user_id: str,
        limit: int = 10,
    ) -> None:
        session_id = self._get_session_id(event)
        entries = self.store.read_recent_audit(
            user_id=str(user_id).strip(),
            session_id=session_id,
            limit=limit,
        )
        if not entries:
            yield event.plain_result("没有找到审计记录。")
            return
        lines = []
        for entry in entries:
            lines.append(
                f"- [{entry['at']}] {entry['action']} {entry['field_name']} "
                f"by {entry['actor_type']}({entry['actor_name']}) | old={entry['old_value']} | new={entry['new_value']}"
            )
        yield event.plain_result("最近画像审计：\n" + "\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像统计")
    async def admin_profile_stats(self, event: AstrMessageEvent) -> None:
        stats = self.store.collect_stats()
        user_count = int(stats["user_count"])
        field_counts = stats["field_counts"]
        custom_field_counts = stats["custom_field_counts"]

        lines = [f"画像用户数：{user_count}", "", "字段覆盖率："]
        for field_name in self.store.builtin_field_map:
            count = int(field_counts.get(field_name, 0))
            ratio = (count / user_count * 100) if user_count else 0.0
            lines.append(f"- {field_name}：{count} ({ratio:.1f}%)")

        if custom_field_counts:
            lines.extend(["", "自定义字段使用情况："])
            for field_name, count in sorted(custom_field_counts.items(), key=lambda item: (-item[1], item[0])):
                lines.append(f"- {field_name}：{count}")

        yield event.plain_result("\n".join(lines))

    async def terminate(self) -> None:
        self._debug("terminate called")
