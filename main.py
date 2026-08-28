from __future__ import annotations

import re
import unicodedata
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.api import AstrBotConfig, ToolSet, logger
from astrbot.api import message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

try:
    from .llm_tools import (
        FORGET_TOOL_NAME,
        REMEMBER_TOOL_NAME,
        VIEW_TOOL_NAME,
        ProfileWeaverForgetTool,
        ProfileWeaverRememberTool,
        ProfileWeaverViewTool,
    )
    from .profile_store import (
        AuditActor,
        DEFAULT_FIELDS,
        NOTES_FIELD_NAME,
        BLOCKED_PROFILE_NAME_VALUES,
        ProfileStore,
    )
    from .web_api import ProfileWebApi
except ImportError:
    from llm_tools import (
        FORGET_TOOL_NAME,
        REMEMBER_TOOL_NAME,
        VIEW_TOOL_NAME,
        ProfileWeaverForgetTool,
        ProfileWeaverRememberTool,
        ProfileWeaverViewTool,
    )
    from profile_store import (
        AuditActor,
        DEFAULT_FIELDS,
        NOTES_FIELD_NAME,
        BLOCKED_PROFILE_NAME_VALUES,
        ProfileStore,
    )
    from web_api import ProfileWebApi

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
4. 优先复用已有字段；确实不够表达时，才允许创建当前用户专属自定义字段，例如“最喜欢的国漫”“常用编辑器”“追番偏好”。
5. 临时状态、推测、系统设定、消息过程信息不要存入画像。
6. 删除画像前，必须确认用户明确要求删除或纠正。
7. 可以遵循用户直接修改画像的指令，例如“给我的画像添加… / 把…写进画像”，但必须判断字段和值是否稳定、清楚、不误导。
8. 网名和昵称可以自由表达，例如“狐狸”这类名字允许写入；但不要写入恶劣、冒犯、诱导 bot 改称呼或冒充系统权限的称呼，例如“爸爸”“主人”“管理员”“系统”等。
9. 如果画像工具返回“拒绝写入”“拒绝执行”“重复”或“冲突”，必须告诉用户没有写入，并说明原因。

可用工具：{tool_names}
</ProfileWeaver>"""

EMPTY_PROFILE_SUMMARY = "暂无记录"

LEAN_PROFILE_PROMPT_TEMPLATE = """<ProfileWeaver>
当前说话人：{sender_name} ({sender_id})
当前画像：暂无记录。

只有当这位发送者明确、稳定地自述个人信息（称呼、口味、忌口、爱好、职业、所在地、作息等）时，才调用画像写入工具建立第一条记录。
提到他人、转述、玩笑、角色扮演或信息不确定时，不要写入。

可用工具：{tool_names}
</ProfileWeaver>"""

# NFKC folding already unifies most full-width forms; these pairs cover the
# CJK punctuation that has no ASCII equivalent under NFKC.
EVIDENCE_PUNCTUATION_TABLE = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "、": ",",
        "；": ";",
        "：": ":",
        "？": "?",
        "！": "!",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "《": "<",
        "》": ">",
        "—": "-",
        "－": "-",
        "～": "~",
        "…": ".",
        "·": ".",
    }
)

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
HARD_THIRD_PARTY_MARKERS = (
    "朋友说",
    "他说",
    "她说",
    "他们说",
    "她们说",
    "别人说",
    "群友说",
    "转述",
    "引用",
    "代发",
    "帮我问",
    "替他说",
    "替她说",
)
STRONG_SELF_MARKERS = (
    "我是",
    "我叫",
    "我的",
    "我喜欢",
    "我爱吃",
    "我不吃",
    "我讨厌",
    "我怕",
    "我来自",
    "我住在",
    "我在",
    "我学",
    "我做",
    "我有",
    "我养",
    "我平时",
    "我通常",
    "我一般",
    "我自己",
    "叫我",
    "请叫我",
    "可以叫我",
    "本人",
)
PROFILE_SIGNAL_MARKERS = (
    "我的",
    "叫我",
    "称呼我",
    "昵称",
    "名字",
    "我是",
    "我叫",
    "喜欢",
    "爱吃",
    "不吃",
    "忌口",
    "过敏",
    "爱好",
    "职业",
    "工作",
    "专业",
    "学生",
    "学校",
    "生日",
    "纪念日",
    "所在地",
    "来自",
    "住在",
    "城市",
    "mbti",
    "宠物",
    "养了",
    "作息",
    "熬夜",
    "早睡",
    "晚睡",
    "害怕",
    "恐惧",
    "弱点",
    "擅长",
    "熟悉",
    "健康",
    "更正",
    "改成",
    "不是",
    "别记",
    "删掉",
    "删除",
    "忘掉",
)
PRIVATE_PROFILE_PREFIXES = (
    "叫我",
    "请叫我",
    "可以叫我",
    "我是",
    "我叫",
    "我喜欢",
    "我爱吃",
    "我不吃",
    "我讨厌",
    "我怕",
    "我来自",
    "我住在",
    "我在",
    "我学",
    "我做",
    "我有",
    "我养",
    "我的",
    "爱吃",
    "不吃",
    "过敏",
    "喜欢",
    "讨厌",
    "来自",
    "住在",
    "学生",
    "职业是",
    "工作是",
    "生日是",
    "mbti是",
)
KNOWN_COMMAND_PREFIXES = (
    "我的画像",
    "画像字段",
    "设置画像",
    "删除画像",
    "清空画像",
    "查询画像",
    "修改画像",
    "删除画像字段",
    "清空用户画像",
    "画像审计",
    "画像统计",
)
AMBIGUOUS_MULTI_SUBJECT_PATTERNS = (
    re.compile(r"我和[^，。！？\s]{1,12}"),
    re.compile(r"我跟[^，。！？\s]{1,12}"),
    re.compile(r"我比(?!较)[^，。！？\s]{1,12}"),
    re.compile(r"和我[^，。！？\s]{1,12}"),
    re.compile(r"跟我[^，。！？\s]{1,12}"),
)
DIRECT_AUTO_FIELD_PATTERN = r"(?P<field>[\u4e00-\u9fffA-Za-z0-9_\-/ ]{1,16}?)"
DIRECT_AUTO_VALUE_PATTERN = r"(?P<value>[^，。！？!?；;\n]{1,120})"
DIRECT_AUTO_PROFILE_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(rf"^我最喜欢的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "最喜欢的{field}", "self_preference"),
    (re.compile(rf"^我最爱的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "最爱的{field}", "self_preference"),
    (re.compile(rf"^我喜欢的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "喜欢的{field}", "self_preference"),
    (re.compile(rf"^我爱看的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "爱看的{field}", "self_preference"),
    (re.compile(rf"^我常看的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "常看的{field}", "self_preference"),
    (re.compile(rf"^我常玩的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "常玩的{field}", "self_preference"),
    (re.compile(rf"^我常用的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "常用的{field}", "self_preference"),
    (re.compile(rf"^我的{DIRECT_AUTO_FIELD_PATTERN}\s*(?:[:：=]|是|为)\s*{DIRECT_AUTO_VALUE_PATTERN}$"), "{field}", "self_report"),
)
DIRECT_AUTO_FIELD_DENY_FRAGMENTS = (
    "@",
    "朋友",
    "群友",
    "别人",
    "他",
    "她",
    "父母",
    "妈妈",
    "爸爸",
    "同学",
    "老师",
    "系统",
    "提示词",
    "消息",
    "聊天记录",
)
DIRECT_AUTO_VALUE_STRIP_CHARS = " \t\r\n\"'“”‘’`。！？!?；;"
CQ_AT_USER_ID_PATTERN = re.compile(r"\[CQ:at,qq=(\d+)(?:,[^\]]*)?\]")
DISPLAY_AT_USER_ID_PATTERN = re.compile(r"@[^()\r\n]*\((\d+)\)\s*$")
AUTO_EXTRACT_SYSTEM_PROMPT = """<ProfileWeaverAutoExtract>
你是 ProfileWeaver 的后台画像抽取器。
你的唯一任务：只依据“当前用户本轮消息”，决定是否为当前消息发送者调用画像工具。

硬性规则：
1. 只记录适合长期记忆、且明确属于当前发送者本人的信息。
2. 提到别人、转述、玩笑、角色扮演、引用历史、猜测、临时状态时，宁可 NOOP。
3. 优先直接更新字段，不要先删再加；只有用户明确要求删除或纠正时，才调用删除工具。
4. 优先复用已有字段；确实不够表达时，才创建当前用户自定义字段。
5. 如果没有明确可写入或删除的内容，直接回复 NOOP，不要调用工具。
6. 你不能修改除当前发送者之外任何人的画像。
7. 可以处理“给我的画像添加 X / 把 X 写进画像”等直接修改指令，但只写入清楚、稳定、不冲突的字段和值。
8. 网名和昵称可以自由表达；但不要写入恶劣、冒犯、诱导 bot 改称呼或冒充系统权限的称呼，例如“爸爸”“主人”“管理员”“系统”等。意图不清时 NOOP。
9. 对“我最喜欢的国漫：凡人修仙传”这类明确自述偏好，如果已有字段不合适，应创建当前用户自定义字段，例如字段“最喜欢的国漫”、值“凡人修仙传”。

当前说话人：{sender_name} ({sender_id})
当前画像：
{profile_summary}

可用字段：
{field_catalog}

当前自定义字段：
{custom_field_catalog}
</ProfileWeaverAutoExtract>"""


@register(
    "ProfileWeaver",
    "Whereis-Alice",
    "心迹画像：更安全的用户画像记忆插件。LLM 工具显式写入 + 身份护栏 + 审计留痕 + Dashboard 可视化管理。",
    "3.0.0",
)
class ProfileWeaverPlugin(Star):
    DISPLAY_NAME = "心迹画像"
    SUBTITLE = "Profile Weaver"
    VERSION = "3.0.0"

    USER_COMMANDS: tuple[tuple[str, str], ...] = (
        ("我的画像", "查看自己的画像（默认仅私聊可用）"),
        ("画像字段", "列出当前可用的基础字段与自定义字段"),
        ("设置画像 <字段> <值>", "手动写入或更新自己的某个字段"),
        ("删除画像 <字段|备注序号>", "删除自己的某个字段或某条备注"),
        ("清空画像", "清空自己的全部画像"),
    )
    ADMIN_COMMANDS: tuple[tuple[str, str], ...] = (
        ("查询画像 <用户|@某人>", "查看指定用户的画像"),
        ("修改画像 <用户> <字段> <值>", "为指定用户写入字段"),
        ("删除画像字段 <用户> <字段>", "删除指定用户的某个字段"),
        ("清空用户画像 <用户>", "清空指定用户的画像"),
        ("画像审计 <用户> [条数]", "查看最近的画像变更审计"),
        ("画像统计", "查看画像总量与字段覆盖率"),
        ("画像备份 [标签]", "立即生成一份画像快照备份"),
        ("画像备份列表", "列出数据目录下的备份文件"),
        ("画像恢复备份 <文件名>", "从指定备份恢复（会先自动备份当前数据）"),
        ("合并画像 <源key> <目标key>", "把两条画像合并成一条，常用于跨会话去重"),
        ("画像面板", "输出 Dashboard 可视化面板的入口说明"),
    )

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
            audit_log_max_mb=self._safe_float(self.config.get("audit_log_max_mb", 8.0), 8.0),
            backup_retention_days=self._safe_int(self.config.get("backup_retention_days", 14), 14),
        )
        self.context.add_llm_tools(
            ProfileWeaverViewTool(plugin=self, active=self._llm_tools_enabled()),
            ProfileWeaverRememberTool(plugin=self, active=self._llm_tools_enabled()),
            ProfileWeaverForgetTool(plugin=self, active=self._llm_tools_enabled()),
        )
        self.auto_extract_tools = ToolSet(
            tools=[
                ProfileWeaverRememberTool(plugin=self, active=True),
                ProfileWeaverForgetTool(plugin=self, active=True),
            ]
        )

        self.web_api: ProfileWebApi | None = None
        if bool(self.config.get("webui_enabled", True)):
            try:
                self.web_api = ProfileWebApi(self)
                registered = self.web_api.register(self.context)
                logger.info(f"[ProfileWeaver] WebUI 已启用，注册 {registered} 个接口。")
            except Exception as exc:
                self.web_api = None
                logger.error(f"[ProfileWeaver] WebUI 接口注册失败，面板将不可用：{exc}")

    # ------------------------------------------------------------- config读取
    @staticmethod
    def _safe_int(raw: Any, fallback: int) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_float(raw: Any, fallback: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return fallback

    def command_catalog(self) -> dict[str, list[dict[str, str]]]:
        return {
            "user": [{"command": name, "desc": desc} for name, desc in self.USER_COMMANDS],
            "admin": [{"command": name, "desc": desc} for name, desc in self.ADMIN_COMMANDS],
        }

    def llm_write_denylist(self) -> list[str]:
        raw = self.config.get("llm_write_denylist") or []
        if isinstance(raw, str):
            raw = [part for part in re.split(r"[,，\s]+", raw) if part]
        names: list[str] = []
        for item in raw:
            canonical = self.store.canonical_field_name(str(item))
            if canonical and canonical not in names:
                names.append(canonical)
        return names

    def _is_llm_write_denied(self, field_name: str) -> bool:
        return self.store.canonical_field_name(field_name) in set(self.llm_write_denylist())

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

    def _proactive_extraction_enabled(self) -> bool:
        return bool(self.config.get("proactive_extraction_enabled", True))

    def _proactive_extraction_min_length(self) -> int:
        return max(4, min(int(self.config.get("proactive_extraction_min_message_length", 4)), 120))

    def _proactive_extraction_max_length(self) -> int:
        min_length = self._proactive_extraction_min_length()
        return max(min_length, min(int(self.config.get("proactive_extraction_max_message_length", 120)), 500))

    def _proactive_extraction_max_steps(self) -> int:
        return max(1, min(int(self.config.get("proactive_extraction_max_steps", 2)), 3))

    def _debug_enabled(self) -> bool:
        return str(self.config.get("debug_log_level", "INFO")).upper() == "DEBUG"

    def _debug(self, message: str) -> None:
        if self._debug_enabled():
            logger.debug(f"[ProfileWeaver] {message}")

    def _get_session_id(self, event: AstrMessageEvent) -> str | None:
        return event.unified_msg_origin if self.session_based else None

    def _resolve_admin_target_user_id(self, event: AstrMessageEvent, raw_target: str) -> str:
        """Prefer the actual ID carried by an At component over its display text."""
        get_messages = getattr(event, "get_messages", None)
        message_chain = get_messages() if callable(get_messages) else []
        if isinstance(message_chain, (list, tuple)):
            for segment in message_chain:
                if not isinstance(segment, Comp.At):
                    continue
                target_user_id = str(getattr(segment, "qq", "")).strip()
                if target_user_id and target_user_id.casefold() != "all":
                    return target_user_id

        target_user_id = str(raw_target or "").strip()
        cq_match = CQ_AT_USER_ID_PATTERN.search(target_user_id)
        if cq_match:
            return cq_match.group(1)
        display_match = DISPLAY_AT_USER_ID_PATTERN.search(target_user_id)
        if display_match:
            return display_match.group(1)
        return target_user_id

    def _build_actor(self, event: AstrMessageEvent, actor_type: str) -> AuditActor:
        return AuditActor(
            actor_type=actor_type,
            actor_id=str(event.get_sender_id()),
            actor_name=str(event.get_sender_name()),
        )

    def _is_group_chat(self, event: AstrMessageEvent) -> bool:
        """Prefer the framework's own private/group signal over UMO string matching."""
        is_private = getattr(event, "is_private_chat", None)
        if callable(is_private):
            try:
                return not bool(is_private())
            except Exception:  # pragma: no cover - adapter dependent
                pass
        get_message_type = getattr(event, "get_message_type", None)
        if callable(get_message_type):
            try:
                message_type = str(get_message_type() or "")
                if message_type:
                    return "group" in message_type.lower()
            except Exception:  # pragma: no cover - adapter dependent
                pass
        origin = str(event.unified_msg_origin or "")
        return "group" in origin.lower()

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        lowered = str(text or "").casefold()
        return any(marker.casefold() in lowered for marker in markers)

    @staticmethod
    def _starts_with_any(text: str, markers: tuple[str, ...]) -> bool:
        lowered = str(text or "").strip().casefold()
        return any(lowered.startswith(marker.casefold()) for marker in markers)

    def _mentions_self(self, text: str) -> bool:
        return self._contains_any(text, FIRST_PERSON_MARKERS)

    def _mentions_strong_self(self, text: str) -> bool:
        return self._contains_any(text, STRONG_SELF_MARKERS)

    def _mentions_third_party(self, text: str) -> bool:
        return self._contains_any(text, THIRD_PARTY_MARKERS)

    def _mentions_hard_third_party(self, text: str) -> bool:
        return self._contains_any(text, HARD_THIRD_PARTY_MARKERS)

    def _is_blocked_profile_label(self, value: str) -> bool:
        return any(token in BLOCKED_PROFILE_NAME_VALUES for token, _ in self.store.extract_conflict_tokens(value))

    @staticmethod
    def _mentions_multi_subject_context(text: str) -> bool:
        raw_text = str(text or "")
        return any(pattern.search(raw_text) for pattern in AMBIGUOUS_MULTI_SUBJECT_PATTERNS)

    @staticmethod
    def _mark_profile_tool_used(event: AstrMessageEvent) -> None:
        setattr(event, "_profileweaver_llm_tool_used", True)

    @staticmethod
    def _profile_tool_was_used(event: AstrMessageEvent) -> bool:
        return bool(getattr(event, "_profileweaver_llm_tool_used", False))

    @staticmethod
    def _set_auto_extract_running(event: AstrMessageEvent, value: bool) -> None:
        setattr(event, "_profileweaver_auto_extract_running", value)

    @staticmethod
    def _is_auto_extract_running(event: AstrMessageEvent) -> bool:
        return bool(getattr(event, "_profileweaver_auto_extract_running", False))

    def _is_ambiguous_identity(self, message_text: str, evidence: str) -> bool:
        if not self._strict_identity_guard():
            return False
        merged_text = f"{message_text}\n{evidence}"
        mentions_third_party = self._mentions_third_party(merged_text)
        mentions_self = self._mentions_self(merged_text)
        return mentions_third_party and not mentions_self

    def _looks_like_command(self, message_text: str) -> bool:
        stripped = str(message_text or "").strip()
        if not stripped:
            return False
        if self._starts_with_any(stripped, KNOWN_COMMAND_PREFIXES):
            return True
        return stripped[:1] in {"/", "!", "."}

    def _is_profile_candidate_message(self, event: AstrMessageEvent, message_text: str) -> bool:
        stripped = str(message_text or "").strip()
        if not stripped:
            return False
        if self._looks_like_command(stripped):
            return False
        if len(stripped) < self._proactive_extraction_min_length():
            return False
        if len(stripped) > self._proactive_extraction_max_length():
            return False
        if stripped.count("\n") >= 3:
            return False
        if any(token in stripped for token in ("http://", "https://", "```", "[CQ:")):
            return False
        if self._mentions_hard_third_party(stripped):
            return False
        if self._mentions_multi_subject_context(stripped):
            return False
        if not self._contains_any(stripped, PROFILE_SIGNAL_MARKERS):
            return False

        has_self = self._mentions_self(stripped)
        if has_self:
            if self._mentions_third_party(stripped) and not self._mentions_strong_self(stripped):
                return False
            return True

        if self._is_group_chat(event):
            return False
        if self._mentions_third_party(stripped):
            return False
        return self._starts_with_any(stripped, PRIVATE_PROFILE_PREFIXES)

    def _parse_direct_auto_profile_update(self, message_text: str) -> tuple[str, str, str] | None:
        stripped = str(message_text or "").strip()
        if not stripped or self._mentions_hard_third_party(stripped) or self._mentions_multi_subject_context(stripped):
            return None

        for pattern, field_template, source_kind in DIRECT_AUTO_PROFILE_PATTERNS:
            match = pattern.fullmatch(stripped)
            if not match:
                continue

            raw_field = str(match.group("field") or "").strip(DIRECT_AUTO_VALUE_STRIP_CHARS)
            value = str(match.group("value") or "").strip(DIRECT_AUTO_VALUE_STRIP_CHARS)
            field_name = field_template.format(field=raw_field).strip(DIRECT_AUTO_VALUE_STRIP_CHARS)
            field_name = re.sub(r"\s+", " ", field_name).strip()
            value = re.sub(r"\s+", " ", value).strip()
            if not field_name or not value:
                return None
            if any(fragment in field_name for fragment in DIRECT_AUTO_FIELD_DENY_FRAGMENTS):
                return None
            if self._mentions_third_party(value):
                return None
            return field_name, value, source_kind

        return None

    def _try_direct_auto_extract_profile(self, event: AstrMessageEvent, message_text: str) -> bool:
        parsed = self._parse_direct_auto_profile_update(message_text)
        if not parsed:
            return False

        field_name, value, source_kind = parsed
        remember_error = self._validate_remember_intent(field_name=field_name, value=value)
        if remember_error:
            self._debug(f"direct auto extraction rejected: {remember_error}")
            return True

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        is_known_field = self.store.is_known_field(user_id, field_name, session_id)
        allow_custom_field = self._allow_llm_custom_fields() and not is_known_field
        if not is_known_field and not allow_custom_field:
            self._debug(f"direct auto extraction skipped: custom field disabled for {field_name}")
            return False

        result = self.store.upsert_field(
            user_id=user_id,
            subject_name=str(event.get_sender_name()),
            field_name=field_name,
            value=value,
            session_id=session_id,
            actor=self._build_actor(event, "auto_extract"),
            source_kind=source_kind,
            evidence=str(message_text or "").strip(),
            allow_custom_field=allow_custom_field,
            field_description="从当前用户明确自述中自动创建的自定义字段",
        )
        self._debug(f"direct auto extraction result for {user_id}: {result.message}")
        return True

    def _build_auto_extract_system_prompt(self, event: AstrMessageEvent) -> str:
        sender_id = str(event.get_sender_id())
        sender_name = str(event.get_sender_name())
        session_id = self._get_session_id(event)
        return AUTO_EXTRACT_SYSTEM_PROMPT.format(
            sender_id=sender_id,
            sender_name=sender_name,
            profile_summary=self.store.format_profile_summary(sender_id, session_id),
            field_catalog=self.store.format_field_catalog(sender_id, session_id),
            custom_field_catalog=self.store.format_custom_field_catalog(sender_id, session_id),
        )

    async def _resolve_chat_provider_id(self, event: AstrMessageEvent) -> str:
        umo = str(event.unified_msg_origin or "")
        if umo:
            try:
                return await self.context.get_current_chat_provider_id(umo)
            except Exception as exc:
                self._debug(f"resolve current provider id failed for {umo}: {exc}")
        provider = self.context.get_using_provider(umo=event.unified_msg_origin)
        if provider is None:
            return ""
        try:
            return str(provider.meta().id or "")
        except Exception as exc:
            self._debug(f"resolve provider meta failed: {exc}")
            return ""

    async def _run_proactive_extraction(self, event: AstrMessageEvent, message_text: str) -> None:
        provider_id = await self._resolve_chat_provider_id(event)
        if not provider_id:
            self._debug("skip proactive extraction: provider id unavailable")
            return

        prompt = (
            "只根据下面这条当前用户消息，决定是否需要调用画像工具。\n"
            f"当前消息：{message_text}\n"
            "如果没有明确、稳定、适合长期记忆的信息，直接回复 NOOP。"
            "可以处理直接修改画像的指令，但不要写入冲突、重复或容易误导的称呼/备注。"
        )
        self._set_auto_extract_running(event, True)
        try:
            response = await self.context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=self._build_auto_extract_system_prompt(event),
                tools=self.auto_extract_tools,
                max_steps=self._proactive_extraction_max_steps(),
                stream=False,
            )
            self._debug(
                "proactive extraction finished with response: "
                f"{str(response.completion_text or '').strip() or '<empty>'}"
            )
        except Exception as exc:
            logger.warning("[ProfileWeaver] proactive extraction failed: %s", exc)
        finally:
            self._set_auto_extract_running(event, False)

    def _build_prompt(self, event: AstrMessageEvent) -> str | None:
        sender_id = str(event.get_sender_id())
        sender_name = str(event.get_sender_name())
        session_id = self._get_session_id(event)
        profile_summary = self.store.format_profile_summary(sender_id, session_id)
        if profile_summary == EMPTY_PROFILE_SUMMARY and not bool(
            self.config.get("inject_when_empty", False)
        ):
            if not self._llm_tools_enabled():
                return None
            return LEAN_PROFILE_PROMPT_TEMPLATE.format(
                sender_name=sender_name,
                sender_id=sender_id,
                tool_names=", ".join([VIEW_TOOL_NAME, REMEMBER_TOOL_NAME, FORGET_TOOL_NAME]),
            )
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
        field_name: str = "",
        value: str = "",
    ) -> str | None:
        message_text = str(event.message_str or "").strip()
        evidence_text = str(evidence or "").strip()
        if source_kind not in allowed_source_kinds:
            return "拒绝执行：source_kind 不在允许范围内。"
        if not message_text:
            return "拒绝执行：当前消息为空，无法校验画像依据。"
        if not evidence_text:
            return "拒绝执行：evidence 不能为空。"
        if not self._evidence_matches_message(evidence_text, message_text):
            return "拒绝执行：evidence 必须直接来自当前用户本轮消息。"
        if source_kind in REMEMBER_SOURCE_KINDS:
            remember_error = self._validate_remember_intent(
                field_name=field_name,
                value=value,
            )
            if remember_error:
                return remember_error
        if self._is_ambiguous_identity(message_text, evidence_text):
            return "拒绝执行：当前消息同时提到其他人且缺少明确自述，容易写错对象。请先澄清，再决定是否记录。"
        if (
            self._mentions_third_party(message_text) or self._mentions_multi_subject_context(message_text)
        ) and not self._mentions_self(evidence_text):
            return "拒绝执行：当前消息提到他人时，evidence 还必须包含明确自述，避免截取成歧义片段。"
        return None

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        """Fold width, drop whitespace and unify CJK/ASCII punctuation for comparison."""
        folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
        folded = folded.translate(EVIDENCE_PUNCTUATION_TABLE)
        return re.sub(r"[\s\u3000]+", "", folded)

    def _evidence_matches_message(self, evidence_text: str, message_text: str) -> bool:
        mode = str(self.config.get("evidence_match_mode", "normalized")).strip().lower()
        if mode == "strict":
            return evidence_text in message_text
        if evidence_text in message_text:
            return True

        normalized_evidence = self._normalize_for_match(evidence_text)
        normalized_message = self._normalize_for_match(message_text)
        if not normalized_evidence:
            return False
        if normalized_evidence in normalized_message:
            return True
        if mode != "loose":
            return False

        # loose: allow lightly rephrased evidence as long as most of it is covered.
        window = 4
        if len(normalized_evidence) <= window:
            return normalized_evidence in normalized_message
        grams = {
            normalized_evidence[index : index + window]
            for index in range(len(normalized_evidence) - window + 1)
        }
        hits = sum(1 for gram in grams if gram in normalized_message)
        return bool(grams) and hits / len(grams) >= 0.7

    def _validate_remember_intent(
        self,
        *,
        field_name: str,
        value: str,
    ) -> str | None:
        if self._is_llm_write_denied(field_name):
            return (
                f"拒绝执行：字段「{field_name}」已被管理员列入 LLM 写入黑名单，只能由用户命令或管理员手动维护。"
                "请告诉用户没有写入，并建议用「设置画像」命令自行填写。"
            )
        if self.store.canonical_field_name(field_name) == NOTES_FIELD_NAME and self._is_blocked_profile_label(value):
            return (
                "拒绝执行：备注值像恶劣、冒犯、诱导或混淆系统身份的称呼，容易误导后续对用户的认知。"
                "请告诉用户没有写入；如果这是爱好、宠物或昵称，请让用户换成更明确的字段和值。"
            )

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
        self._mark_profile_tool_used(event)
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
        self._mark_profile_tool_used(event)
        if not self._llm_tools_enabled():
            return "画像工具当前已关闭。"
        field_name = str(kwargs.get("field_name") or "").strip()
        value = str(kwargs.get("value") or "").strip()
        evidence = str(kwargs.get("evidence") or "").strip()
        source_kind = str(kwargs.get("source_kind") or "").strip()
        create_custom_field = bool(kwargs.get("create_custom_field", False))
        field_description = str(kwargs.get("field_description") or "").strip()

        validation_error = self._validate_evidence(
            event,
            evidence,
            REMEMBER_SOURCE_KINDS,
            source_kind,
            field_name=field_name,
            value=value,
        )
        if validation_error:
            return validation_error

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        field_is_known = self.store.is_known_field(user_id, field_name, session_id)
        effective_create_custom_field = create_custom_field or (
            self._allow_llm_custom_fields() and not field_is_known
        )
        field_error = self._ensure_known_or_creatable_field(
            user_id=user_id,
            session_id=session_id,
            field_name=field_name,
            create_custom_field=effective_create_custom_field,
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
            allow_custom_field=self._allow_llm_custom_fields() and effective_create_custom_field,
            field_description=field_description,
        )
        self._debug(f"LLM remember result for {user_id}: {result.message}")
        return result.message

    async def handle_llm_forget(
        self,
        event: AstrMessageEvent,
        **kwargs: Any,
    ) -> str:
        self._mark_profile_tool_used(event)
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
        if self._is_auto_extract_running(event):
            return
        prompt = self._build_prompt(event)
        if prompt is None:
            return
        current_system_prompt = str(req.system_prompt or "").rstrip()
        req.system_prompt = f"{current_system_prompt}\n\n{prompt}".strip()

    @filter.on_llm_response()
    async def maybe_auto_extract_profile(self, event: AstrMessageEvent, response: LLMResponse) -> None:
        if not self._llm_tools_enabled() or not self._proactive_extraction_enabled():
            return
        if self._is_auto_extract_running(event):
            return
        if self._profile_tool_was_used(event):
            self._debug("skip proactive extraction: profile tool already used in main run")
            return

        tool_names = set(getattr(response, "tools_call_name", []) or [])
        if tool_names & {VIEW_TOOL_NAME, REMEMBER_TOOL_NAME, FORGET_TOOL_NAME}:
            self._debug("skip proactive extraction: response already contains profile tool calls")
            return

        message_text = str(event.message_str or "").strip()
        if not self._is_profile_candidate_message(event, message_text):
            return

        if self._try_direct_auto_extract_profile(event, message_text):
            return

        self._debug(f"trigger proactive extraction for sender {event.get_sender_id()}")
        await self._run_proactive_extraction(event, message_text)

    @filter.command("我的画像")
    async def show_my_profile(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
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
        if summary == EMPTY_PROFILE_SUMMARY:
            yield event.plain_result("暂时还没有你的画像记录。")
            return

        last_updated = self.store.get_last_updated(user_id, session_id) or "未知"
        yield event.plain_result(f"你的画像：\n{summary}\n\n最后更新：{last_updated}")

    @filter.command("画像字段")
    async def show_field_catalog(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        catalog = self.store.format_field_catalog(user_id, session_id)
        yield event.plain_result(f"可用画像字段：\n{catalog}")

    @filter.command("设置画像")
    async def set_my_profile(self, event: AstrMessageEvent, field_name: str, value: str) -> AsyncGenerator[Any, None]:
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
    async def delete_my_profile(self, event: AstrMessageEvent, field_selector: str) -> AsyncGenerator[Any, None]:
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
    async def clear_my_profile(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        result = self.store.clear_profile(
            user_id=str(event.get_sender_id()),
            session_id=self._get_session_id(event),
            actor=self._build_actor(event, "user_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查询画像")
    async def admin_query_profile(self, event: AstrMessageEvent, user_id: str) -> AsyncGenerator[Any, None]:
        target_user_id = self._resolve_admin_target_user_id(event, user_id)
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
    ) -> AsyncGenerator[Any, None]:
        target_user_id = self._resolve_admin_target_user_id(event, user_id)
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
    ) -> AsyncGenerator[Any, None]:
        result = self.store.delete_field(
            user_id=self._resolve_admin_target_user_id(event, user_id),
            session_id=self._get_session_id(event),
            field_selector=field_selector,
            actor=self._build_actor(event, "admin_command"),
            source_kind="admin_delete",
            evidence=str(event.message_str or ""),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("清空用户画像")
    async def admin_clear_profile(self, event: AstrMessageEvent, user_id: str) -> AsyncGenerator[Any, None]:
        result = self.store.clear_profile(
            user_id=self._resolve_admin_target_user_id(event, user_id),
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
    ) -> AsyncGenerator[Any, None]:
        session_id = self._get_session_id(event)
        entries = self.store.read_recent_audit(
            user_id=self._resolve_admin_target_user_id(event, user_id),
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
    async def admin_profile_stats(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        stats = self.store.collect_stats()
        profile_count = int(stats.get("profile_count") or stats.get("user_count") or 0)
        field_counts = stats.get("field_counts", {})
        custom_field_counts = stats.get("custom_field_counts", {})

        lines = [
            f"画像总数：{profile_count}（独立用户 {int(stats.get('user_count') or 0)}，会话 {int(stats.get('session_count') or 0)}）",
            f"已填字段：{int(stats.get('filled_field_count') or 0)}，人均 {float(stats.get('avg_fields_per_profile') or 0):.1f} 个",
            f"近 7 天活跃：{int(stats.get('active_profiles_7d') or 0)}，最后更新：{stats.get('latest_updated_at') or '未知'}",
            f"数据体积：画像 {self._format_bytes(stats.get('profiles_file_bytes'))}，审计 {self._format_bytes(stats.get('audit_log_bytes'))}",
            "",
            "字段覆盖率（Top 10）：",
        ]
        ranked = sorted(
            self.store.builtin_field_map.keys(),
            key=lambda name: (-int(field_counts.get(name, 0)), name),
        )
        for field_name in ranked[:10]:
            count = int(field_counts.get(field_name, 0))
            ratio = (count / profile_count * 100) if profile_count else 0.0
            lines.append(f"- {field_name}：{count} ({ratio:.1f}%)")

        if custom_field_counts:
            lines.extend(["", "自定义字段使用情况（Top 10）："])
            for field_name, count in sorted(
                custom_field_counts.items(), key=lambda item: (-item[1], item[0])
            )[:10]:
                lines.append(f"- {field_name}：{count}")

        source_counts = stats.get("source_counts") or {}
        if source_counts:
            summary = "、".join(
                f"{name} {count}"
                for name, count in sorted(source_counts.items(), key=lambda item: -item[1])[:5]
            )
            lines.extend(["", f"写入来源：{summary}"])

        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像备份")
    async def admin_create_backup(
        self,
        event: AstrMessageEvent,
        tag: str = "manual",
    ) -> AsyncGenerator[Any, None]:
        path = self.store.create_backup(tag)
        if path is None:
            yield event.plain_result("❌ 备份失败，请检查数据目录写入权限。")
            return
        yield event.plain_result(f"✅ 已创建备份：{path.name}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像备份列表")
    async def admin_list_backups(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        backups = self.store.list_backups()
        if not backups:
            yield event.plain_result("暂无备份文件。可以先执行「画像备份」。")
            return
        lines = [
            f"- {item['name']}（{self._format_bytes(item.get('size'))}，{item.get('modified_at')}）"
            for item in backups[:20]
        ]
        yield event.plain_result(f"共 {len(backups)} 个备份：\n" + "\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像恢复备份")
    async def admin_restore_backup(
        self,
        event: AstrMessageEvent,
        name: str,
    ) -> AsyncGenerator[Any, None]:
        result = self.store.restore_backup(name, self._build_actor(event, "admin_command"))
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("合并画像")
    async def admin_merge_profiles(
        self,
        event: AstrMessageEvent,
        source_key: str,
        target_key: str,
    ) -> AsyncGenerator[Any, None]:
        result = self.store.merge_profile_records(
            source_key=source_key,
            target_key=target_key,
            actor=self._build_actor(event, "admin_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像面板")
    async def admin_webui_hint(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        if self.web_api is None:
            yield event.plain_result(
                "WebUI 未启用。请在插件配置里打开「是否启用 WebUI 画像管理面板」，然后重载插件。"
            )
            return
        stats = self.store.collect_stats()
        yield event.plain_result(
            f"{self.DISPLAY_NAME} 面板已就绪：\n"
            "打开 AstrBot Dashboard → 插件管理 → 心迹画像 → 画像面板。\n"
            f"当前 {int(stats.get('profile_count') or 0)} 条画像，"
            f"写操作{'已开启' if self.config.get('webui_allow_edit', True) else '已锁定（只读）'}。\n"
            "面板接口仅依赖 Dashboard 登录态，请不要把 Dashboard 暴露到公网。"
        )

    @staticmethod
    def _format_bytes(raw_size: Any) -> str:
        try:
            size = float(raw_size or 0)
        except (TypeError, ValueError):
            return "0 B"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    async def terminate(self) -> None:
        self._debug("terminate called")
