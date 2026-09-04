"""ProfileWeaver / 心迹画像 —— AstrBot 用户画像记忆插件主入口。

注意：本文件刻意不使用 ``from __future__ import annotations``。
AstrBot 的 CommandFilter 用 ``annotation is GreedyStr`` 做身份比较来识别贪婪参数，
一旦启用 PEP 563 延迟注解，注解会退化成字符串 "GreedyStr"，贪婪参数将静默失效，
导致「设置画像 昵称 小 明」这类带空格的参数被悄悄截断。
"""

import re
import unicodedata
from collections.abc import AsyncGenerator
from typing import Any

from astrbot.api import AstrBotConfig, ToolSet, logger
from astrbot.api import message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

try:  # GreedyStr 未从 astrbot.api 导出，只能深层导入
    from astrbot.core.star.filter.command import GreedyStr
except ImportError:  # pragma: no cover - 兼容更旧版本的 AstrBot
    GreedyStr = str  # type: ignore[assignment,misc]

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
        BLOCKED_PROFILE_NAME_VALUES,
        DEFAULT_FIELD_LOCK_SCOPE,
        DEFAULT_FIELDS,
        EMPTY_PROFILE_SUMMARY,
        FIELD_LOCK_SCOPE_LABELS,
        NOTES_FIELD_NAME,
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
        BLOCKED_PROFILE_NAME_VALUES,
        DEFAULT_FIELD_LOCK_SCOPE,
        DEFAULT_FIELDS,
        EMPTY_PROFILE_SUMMARY,
        FIELD_LOCK_SCOPE_LABELS,
        NOTES_FIELD_NAME,
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
# 他人指代检测。这里必须用正则而不是裸子串：
#   * 「他」会命中「其他 / 吉他 / 维他命 / 他妈的」，「我喜欢弹吉他」这种典型自述会被误拒；
#   * casefold 后的 "ta" 会命中 data / status / detail / metadata / guitar / total；
#   * 裸 "@" 会命中邮箱。
# 一旦误判，_validate_evidence 会直接拒写，属于静默丢数据的严重问题。
_THIRD_PARTY_HE = r"(?<![其吉維维利排])他(?!妈(?!妈)|娘(?!家))"
THIRD_PARTY_PATTERN = re.compile(
    "|".join(
        (
            r"(?<![0-9A-Za-z._+\-])@",  # @某人，但不误伤 a@b.com
            _THIRD_PARTY_HE,
            r"她",
            r"(?<![0-9A-Za-z])ta(?![0-9A-Za-z])",  # \b 对 CJK 无效，只能显式排除拉丁字母数字
            r"别人",
            r"群友",
            r"朋友说",
        )
    ),
    re.IGNORECASE,
)
HARD_THIRD_PARTY_PATTERN = re.compile(
    "|".join(
        (
            r"朋友说",
            r"(?<![其吉維维利排])[他她](?:们)?说",
            r"别人说",
            r"群友说",
            r"转述",
            r"引用",
            r"代发",
            r"帮我问",
            r"替[他她]说",
        )
    )
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
# 字段名黑名单：同样不能用裸子串，否则「我的吉他是 Fender」会因为「吉他」含「他」被拒。
DIRECT_AUTO_FIELD_DENY_PATTERN = re.compile(
    "|".join(
        (
            r"@",
            r"朋友",
            r"群友",
            r"别人",
            _THIRD_PARTY_HE,
            r"她",
            r"父母",
            r"妈妈",
            r"爸爸",
            r"同学",
            r"老师",
            r"系统",
            r"提示词",
            r"消息",
            r"聊天记录",
        )
    )
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

# 审计动作的中文展示名，命令行与 WebUI 共用同一套措辞。
AUDIT_ACTION_LABELS: dict[str, str] = {
    "upsert_field": "写入字段",
    "append_note": "追加备注",
    "delete_field": "删除字段",
    "delete_note": "删除备注",
    "lock_field": "锁定字段",
    "unlock_field": "解锁字段",
    "clear_profile": "清空画像",
    "delete_profile": "删除画像",
    "merge_profile": "合并画像",
    "import_bundle": "导入数据",
    "restore_backup": "恢复备份",
    "delete_backup": "删除备份",
}
PROGRESS_BAR_WIDTH = 20


@register(
    "ProfileWeaver",
    "Whereis-Alice",
    "心迹画像：更安全的用户画像记忆插件。LLM 工具显式写入 + 身份护栏 + 字段锁 + 审计留痕 + Dashboard 可视化管理。",
    "3.1.0",
)
class ProfileWeaverPlugin(Star):
    DISPLAY_NAME = "心迹画像"
    SUBTITLE = "Profile Weaver"
    VERSION = "3.1.0"

    USER_COMMANDS: tuple[tuple[str, str], ...] = (
        ("我的画像", "查看自己的画像（默认仅私聊可用）"),
        ("画像字段", "列出当前可用的基础字段与自定义字段"),
        ("画像完整度", "查看画像填写进度、锁定情况与还缺哪些字段"),
        ("设置画像 <字段> <值>", "手动写入或更新自己的某个字段"),
        ("删除画像 <字段|备注序号>", "删除自己的某个字段或某条备注"),
        ("锁定画像 <字段>", "锁定字段，阻止 LLM 与自动抽取改写"),
        ("解锁画像 <字段>", "解除某个字段的锁定"),
        ("画像历史 <字段>", "查看自己某个字段的变更历史"),
        ("清空画像", "清空自己的全部画像"),
        ("画像帮助", "列出全部画像指令与当前功能开关"),
    )
    ADMIN_COMMANDS: tuple[tuple[str, str], ...] = (
        ("查询画像 <用户|@某人>", "查看指定用户的画像"),
        ("修改画像 <用户> <字段> <值>", "为指定用户写入字段"),
        ("删除画像字段 <用户> <字段>", "删除指定用户的某个字段"),
        ("清空用户画像 <用户>", "清空指定用户的画像"),
        ("锁定用户画像 <用户> <字段>", "锁定指定用户的某个字段"),
        ("解锁用户画像 <用户> <字段>", "解锁指定用户的某个字段"),
        ("画像字段历史 <用户> <字段>", "查看指定用户某个字段的变更历史"),
        ("画像审计 <用户> [条数]", "查看最近的画像变更审计"),
        ("画像统计", "查看画像总量、完整度与字段覆盖率"),
        ("画像备份 [标签]", "立即生成一份画像快照备份"),
        ("画像备份列表", "列出数据目录下的备份文件"),
        ("画像恢复备份 <文件名>", "从指定备份恢复（会先自动备份当前数据）"),
        ("合并画像 <源key> <目标key>", "把两条画像合并成一条，常用于跨会话去重"),
        ("画像面板", "输出 Dashboard 可视化面板的入口说明"),
    )
    _command_prefix_cache: tuple[str, ...] | None = None

    @classmethod
    def command_prefixes(cls) -> tuple[str, ...]:
        """从指令表推导出全部指令名，避免新增指令时漏改命令护栏名单。"""
        if cls._command_prefix_cache is None:
            names = {
                str(spec).split(" ", 1)[0].strip()
                for spec, _ in (*cls.USER_COMMANDS, *cls.ADMIN_COMMANDS)
                if str(spec).strip()
            }
            cls._command_prefix_cache = tuple(sorted(names, key=lambda item: (-len(item), item)))
        return cls._command_prefix_cache

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        data_dir = StarTools.get_data_dir()
        default_fields = self.config.get("default_fields") or self.config.get("allowed_fields") or [
            name for name, _ in DEFAULT_FIELDS
        ]
        default_fields = self._adopt_new_builtin_fields(default_fields)
        self.store = ProfileStore(
            data_dir=data_dir,
            builtin_fields=default_fields,
            max_notes_count=self.config.get("max_notes_count", 5),
            custom_field_name_max_length=self.config.get("custom_field_name_max_length", 16),
            field_value_max_length=self.config.get("field_value_max_length", 160),
            audit_log_max_mb=self._safe_float(self.config.get("audit_log_max_mb", 8.0), 8.0),
            backup_retention_days=self._safe_int(self.config.get("backup_retention_days", 14), 14),
            field_lock_scope=str(self.config.get("field_lock_scope", DEFAULT_FIELD_LOCK_SCOPE)),
            audit_log_keep_rotated=self._safe_int(self.config.get("audit_log_keep_rotated", 5), 5),
            backup_max_count=self._safe_int(self.config.get("backup_max_count", 60), 60),
        )
        self._llm_tools_active = self._llm_tools_enabled()
        self.context.add_llm_tools(
            ProfileWeaverViewTool(plugin=self, active=self._llm_tools_active),
            ProfileWeaverRememberTool(plugin=self, active=self._llm_tools_active),
            ProfileWeaverForgetTool(plugin=self, active=self._llm_tools_active),
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
    def _adopt_new_builtin_fields(self, configured: Any) -> list[str]:
        """插件升级时把新增的内置字段并入用户已有配置，保持原顺序，且每个版本只做一次。

        list 型配置不会被 AstrBot 的 schema 默认值补齐，如果不做这一步，
        老用户升级后永远看不到新版本新增的基础字段。
        """
        names = [str(item).strip() for item in (configured or []) if str(item).strip()]
        if not bool(self.config.get("auto_adopt_new_builtin_fields", True)):
            return names
        if str(self.config.get("builtin_fields_adopted_version") or "") == self.VERSION:
            return names

        merged = list(names)
        seen = set(merged)
        for name, _ in DEFAULT_FIELDS:
            if name not in seen:
                merged.append(name)
                seen.add(name)

        self.config["builtin_fields_adopted_version"] = self.VERSION
        if merged != names:
            self.config["default_fields"] = merged
            logger.info(
                f"[ProfileWeaver] 已并入 v{self.VERSION} 新增的基础字段，当前共 {len(merged)} 个。"
            )
        try:
            self.config.save_config()
        except Exception as exc:  # pragma: no cover - 取决于宿主写入权限
            logger.warning(f"[ProfileWeaver] 字段配置保存失败，下次启动会重试：{exc}")
        return merged

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

    def _sync_llm_tool_activation(self) -> None:
        """把「是否启用 LLM 工具」的运行时配置同步到工具管理器。

        注册时的 active 只在 __init__ 求值一次，用户在面板上改了开关后不会生效，
        这里在每次 LLM 请求前对比一次，必要时激活/停用。
        """
        desired = self._llm_tools_enabled()
        if desired == getattr(self, "_llm_tools_active", desired):
            return
        for tool_name in (VIEW_TOOL_NAME, REMEMBER_TOOL_NAME, FORGET_TOOL_NAME):
            try:
                if desired:
                    self.context.activate_llm_tool(tool_name)
                else:
                    self.context.deactivate_llm_tool(tool_name)
            except Exception as exc:  # pragma: no cover - 取决于宿主实现
                self._debug(f"同步 LLM 工具 {tool_name} 状态失败：{exc}")
        self._llm_tools_active = desired
        self._debug(f"LLM 工具激活状态已同步为 {desired}")

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

    @staticmethod
    def _mentions_third_party(text: str) -> bool:
        return bool(THIRD_PARTY_PATTERN.search(str(text or "")))

    @staticmethod
    def _mentions_hard_third_party(text: str) -> bool:
        return bool(HARD_THIRD_PARTY_PATTERN.search(str(text or "")))

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
        if self._starts_with_any(stripped, self.command_prefixes()):
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
            if DIRECT_AUTO_FIELD_DENY_PATTERN.search(field_name):
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
        self._sync_llm_tool_activation()
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
        denied = self._group_privacy_denied(event)
        if denied:
            yield event.plain_result(denied)
            return

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        summary = self.store.format_profile_summary(user_id, session_id)
        if summary == EMPTY_PROFILE_SUMMARY:
            yield event.plain_result("暂时还没有你的画像记录。")
            return

        overview = self.store.summarize_profile(
            self.store.profile_key(user_id, session_id),
            self.store.get_profile(user_id, session_id),
        )
        percent = float(overview.get("completeness") or 0.0)
        footer = f"完整度 {percent:.0f}%  {self._progress_bar(percent, 10)}"
        locked_count = int(overview.get("locked_count") or 0)
        if locked_count:
            footer += f"　·　已锁定 {locked_count} 个字段"
        last_updated = self.store.get_last_updated(user_id, session_id) or "未知"
        yield event.plain_result(
            f"你的画像：\n{summary}\n\n{footer}\n最后更新：{last_updated}"
        )

    @filter.command("画像字段")
    async def show_field_catalog(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        catalog = self.store.format_field_catalog(user_id, session_id)
        yield event.plain_result(f"可用画像字段：\n{catalog}")

    @filter.command("画像完整度")
    async def show_my_completeness(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        denied = self._group_privacy_denied(event)
        if denied:
            yield event.plain_result(denied)
            return

        user_id = str(event.get_sender_id())
        session_id = self._get_session_id(event)
        record = self.store.get_profile(user_id, session_id)
        if not record:
            yield event.plain_result(
                "还没有你的画像记录。可以先用「设置画像 <字段> <值>」写第一条，"
                "或者直接和我聊聊你自己。"
            )
            return

        overview = self.store.summarize_profile(
            self.store.profile_key(user_id, session_id), record
        )
        percent = float(overview.get("completeness") or 0.0)
        fields = record.get("fields") or {}
        builtin_names = list(self.store.builtin_field_map)
        filled = [name for name in builtin_names if fields.get(name)]
        missing = [name for name in builtin_names if not fields.get(name)]
        lines = [
            f"画像完整度：{percent:.1f}%",
            self._progress_bar(percent),
            f"基础字段 {len(filled)}/{len(builtin_names)}　·　"
            f"自定义字段 {int(overview.get('custom_field_count') or 0)} 个　·　"
            f"备注 {int(overview.get('note_count') or 0)} 条",
        ]
        locked_fields = overview.get("locked_fields") or []
        if locked_fields:
            lines.append(f"🔒 已锁定 {len(locked_fields)} 个：{'、'.join(locked_fields)}")
        if missing:
            preview = "、".join(missing[:12])
            more = f"…（共 {len(missing)} 项）" if len(missing) > 12 else ""
            lines.append(f"还没填：{preview}{more}")
        else:
            lines.append("基础字段都填满了，非常完整 ✨")
        yield event.plain_result("\n".join(lines))

    @filter.command("设置画像")
    async def set_my_profile(
        self,
        event: AstrMessageEvent,
        field_name: str,
        value: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
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
    async def delete_my_profile(
        self,
        event: AstrMessageEvent,
        field_selector: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        result = self.store.delete_field(
            user_id=str(event.get_sender_id()),
            session_id=self._get_session_id(event),
            field_selector=field_selector,
            actor=self._build_actor(event, "user_command"),
            source_kind="manual_delete",
            evidence=str(event.message_str or ""),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.command("锁定画像")
    async def lock_my_field(
        self,
        event: AstrMessageEvent,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        yield event.plain_result(
            self._apply_field_lock(
                event,
                target_user_id=str(event.get_sender_id()),
                field_name=field_name,
                locked=True,
                actor_type="user_command",
            )
        )

    @filter.command("解锁画像")
    async def unlock_my_field(
        self,
        event: AstrMessageEvent,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        yield event.plain_result(
            self._apply_field_lock(
                event,
                target_user_id=str(event.get_sender_id()),
                field_name=field_name,
                locked=False,
                actor_type="user_command",
            )
        )

    @filter.command("画像历史")
    async def show_my_field_history(
        self,
        event: AstrMessageEvent,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        denied = self._group_privacy_denied(event)
        if denied:
            yield event.plain_result(denied)
            return

        raw_field, limit = self._split_trailing_limit(field_name, default_limit=10, max_limit=30)
        if not raw_field:
            yield event.plain_result("用法：画像历史 <字段> [条数]，例如「画像历史 昵称」。")
            return
        yield event.plain_result(
            self._format_field_history(
                user_id=str(event.get_sender_id()),
                session_id=self._get_session_id(event),
                field_name=raw_field,
                limit=limit,
            )
        )

    @filter.command("清空画像")
    async def clear_my_profile(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        result = self.store.clear_profile(
            user_id=str(event.get_sender_id()),
            session_id=self._get_session_id(event),
            actor=self._build_actor(event, "user_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.command("画像帮助")
    async def show_profile_help(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        lines = [
            f"{self.DISPLAY_NAME} · {self.SUBTITLE} v{self.VERSION}",
            "",
            "【常用指令】",
        ]
        lines.extend(f"· {name} —— {desc}" for name, desc in self.USER_COMMANDS)
        if event.is_admin():
            lines.extend(["", "【管理员指令】"])
            lines.extend(f"· {name} —— {desc}" for name, desc in self.ADMIN_COMMANDS)
        lines.extend(
            [
                "",
                "【当前状态】",
                f"· LLM 画像工具：{'已启用' if self._llm_tools_enabled() else '已关闭'}",
                f"· 自动抽取兜底：{'已启用' if self._proactive_extraction_enabled() else '已关闭'}",
                f"· 画像作用域：{'按会话隔离' if self.session_based else '全局共享'}",
                f"· 字段锁范围：{self.store.field_lock_scope_label()}",
                "· 群聊查看画像："
                f"{'允许' if self.config.get('allow_profile_in_group', False) else '仅私聊'}",
                f"· WebUI 面板：{'已就绪' if self.web_api is not None else '未启用'}",
            ]
        )
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("查询画像")
    async def admin_query_profile(
        self,
        event: AstrMessageEvent,
        user_id: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        target_user_id = self._resolve_admin_target_user_id(event, user_id)
        session_id = self._get_session_id(event)
        summary = self.store.format_profile_summary(target_user_id, session_id)
        if summary == EMPTY_PROFILE_SUMMARY:
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
        value: GreedyStr,
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
        field_selector: GreedyStr,
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
    async def admin_clear_profile(
        self,
        event: AstrMessageEvent,
        user_id: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        result = self.store.clear_profile(
            user_id=self._resolve_admin_target_user_id(event, user_id),
            session_id=self._get_session_id(event),
            actor=self._build_actor(event, "admin_command"),
        )
        yield event.plain_result(("✅ " if result.ok else "❌ ") + result.message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("锁定用户画像")
    async def admin_lock_field(
        self,
        event: AstrMessageEvent,
        user_id: str,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        yield event.plain_result(
            self._apply_field_lock(
                event,
                target_user_id=self._resolve_admin_target_user_id(event, user_id),
                field_name=field_name,
                locked=True,
                actor_type="admin_command",
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("解锁用户画像")
    async def admin_unlock_field(
        self,
        event: AstrMessageEvent,
        user_id: str,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        yield event.plain_result(
            self._apply_field_lock(
                event,
                target_user_id=self._resolve_admin_target_user_id(event, user_id),
                field_name=field_name,
                locked=False,
                actor_type="admin_command",
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像字段历史")
    async def admin_field_history(
        self,
        event: AstrMessageEvent,
        user_id: str,
        field_name: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        raw_field, limit = self._split_trailing_limit(field_name, default_limit=10, max_limit=30)
        if not raw_field:
            yield event.plain_result("用法：画像字段历史 <用户|@某人> <字段> [条数]")
            return
        target_user_id = self._resolve_admin_target_user_id(event, user_id)
        yield event.plain_result(
            self._format_field_history(
                user_id=target_user_id,
                session_id=self._get_session_id(event),
                field_name=raw_field,
                limit=limit,
                subject_label=f"用户 {target_user_id} 的",
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像审计")
    async def admin_audit_profile(
        self,
        event: AstrMessageEvent,
        target: GreedyStr,
    ) -> AsyncGenerator[Any, None]:
        # 用单个贪婪参数接收「<用户> [条数]」，否则 @某人(123) 里的空格会把参数切碎。
        raw_target, limit = self._split_trailing_limit(target, default_limit=10)
        if not raw_target:
            yield event.plain_result("用法：画像审计 <用户|@某人> [条数]")
            return
        session_id = self._get_session_id(event)
        entries = self.store.read_recent_audit(
            user_id=self._resolve_admin_target_user_id(event, raw_target),
            session_id=session_id,
            limit=limit,
            include_rotated=True,
        )
        if not entries:
            yield event.plain_result("没有找到审计记录。")
            return
        lines = []
        for entry in entries:
            action = str(entry.get("action") or "")
            lines.append(
                f"- [{entry.get('at')}] {AUDIT_ACTION_LABELS.get(action, action)} "
                f"{entry.get('field_name') or '-'} by {entry.get('actor_type')}"
                f"({entry.get('actor_name') or entry.get('actor_id') or '-'})"
            )
            lines.append(
                f"  {entry.get('old_value') or '（空）'} → {entry.get('new_value') or '（空）'}"
            )
        yield event.plain_result(
            f"最近 {len(entries)} 条画像审计：\n" + "\n".join(lines)
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("画像统计")
    async def admin_profile_stats(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        stats = self.store.collect_stats()
        profile_count = int(stats.get("profile_count") or stats.get("user_count") or 0)
        field_counts = stats.get("field_counts", {})
        custom_field_counts = stats.get("custom_field_counts", {})

        avg_completeness = float(stats.get("avg_completeness") or 0.0)
        lines = [
            f"画像总数：{profile_count}（独立用户 {int(stats.get('user_count') or 0)}，会话 {int(stats.get('session_count') or 0)}）",
            f"已填字段：{int(stats.get('filled_field_count') or 0)}，人均 {float(stats.get('avg_fields_per_profile') or 0):.1f} 个",
            f"平均完整度：{avg_completeness:.1f}%  {self._progress_bar(avg_completeness, 10)}",
            f"活跃画像：近 7 天 {int(stats.get('active_profiles_7d') or 0)}，"
            f"近 30 天 {int(stats.get('active_profiles_30d') or 0)}",
            f"最后更新：{stats.get('latest_updated_at') or '未知'}",
            f"字段锁：{int(stats.get('locked_field_count') or 0)} 个字段被锁"
            f"（涉及 {int(stats.get('locked_profile_count') or 0)} 条画像）"
            f"，范围＝{stats.get('field_lock_scope_label') or self.store.field_lock_scope_label()}",
            f"数据体积：画像 {self._format_bytes(stats.get('profiles_file_bytes'))}，"
            f"审计 {self._format_bytes(stats.get('audit_log_bytes'))}",
            f"备份 {int(stats.get('backup_count') or 0)} 份，"
            f"审计归档 {int(stats.get('audit_rotated_count') or 0)} 份",
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
        name: GreedyStr,
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

    # ------------------------------------------------------- 字段锁 / 历史工具
    @staticmethod
    def _split_trailing_limit(
        raw: str,
        *,
        default_limit: int,
        max_limit: int = 50,
    ) -> tuple[str, int]:
        """把「<目标> [条数]」拆开：只有末尾是纯数字才当条数，其余整体作为目标。

        贪婪参数必须放在最后，所以带空格的目标（例如 @某 人(123)）没法再跟一个
        独立的 int 参数，这里手动还原「可选条数」的语义。
        """
        tokens = str(raw or "").split()
        limit = default_limit
        if len(tokens) > 1 and tokens[-1].isdigit():
            limit = max(1, min(int(tokens[-1]), max_limit))
            tokens = tokens[:-1]
        return " ".join(tokens).strip(), limit

    @staticmethod
    def _progress_bar(percent: float, width: int = PROGRESS_BAR_WIDTH) -> str:
        try:
            ratio = max(0.0, min(float(percent or 0.0), 100.0)) / 100
        except (TypeError, ValueError):
            ratio = 0.0
        done = int(round(ratio * width))
        return "█" * done + "░" * max(0, width - done)

    def _group_privacy_denied(self, event: AstrMessageEvent) -> str | None:
        """群聊里默认不回显画像内容；返回拒绝文案，或 None 表示允许。"""
        if not self._is_group_chat(event):
            return None
        if bool(self.config.get("allow_profile_in_group", False)):
            return None
        return str(
            self.config.get(
                "group_profile_denied_msg",
                "画像内容可能涉及隐私，请私聊查看。",
            )
        )

    def _apply_field_lock(
        self,
        event: AstrMessageEvent,
        *,
        target_user_id: str,
        field_name: str,
        locked: bool,
        actor_type: str,
    ) -> str:
        field_name = str(field_name or "").strip()
        if not field_name:
            verb = "锁定" if locked else "解锁"
            return f"❌ 用法：{verb}画像 <字段>，例如「{verb}画像 昵称」。"

        session_id = self._get_session_id(event)
        record = self.store.get_profile(target_user_id, session_id)
        subject_name = str(record.get("subject_name") or "")
        if not subject_name and target_user_id == str(event.get_sender_id()):
            subject_name = str(event.get_sender_name())
        result = self.store.set_field_lock(
            user_id=target_user_id,
            subject_name=subject_name or target_user_id,
            session_id=session_id,
            field_name=field_name,
            locked=locked,
            actor=self._build_actor(event, actor_type),
        )
        suffix = ""
        if result.ok and locked:
            suffix = f"\n当前锁范围：{self.store.field_lock_scope_label()}"
        return ("✅ " if result.ok else "❌ ") + result.message + suffix

    def _format_field_history(
        self,
        *,
        user_id: str,
        session_id: str | None,
        field_name: str,
        limit: int = 10,
        subject_label: str = "",
    ) -> str:
        canonical = self.store.canonical_field_name(field_name)
        if not canonical:
            return f"❌ 认不出字段「{field_name}」，可以先用「画像字段」看看有哪些字段。"
        entries = self.store.read_field_history(
            user_id=user_id,
            session_id=session_id,
            field_name=canonical,
            limit=limit,
        )
        if not entries:
            return f"{subject_label}字段「{canonical}」还没有变更记录。"
        lines = [f"{subject_label}字段「{canonical}」最近 {len(entries)} 条变更："]
        for entry in entries:
            action = str(entry.get("action") or "")
            lines.append(
                f"- [{entry.get('at')}] {AUDIT_ACTION_LABELS.get(action, action)} "
                f"by {entry.get('actor_type')}"
                f"({entry.get('actor_name') or entry.get('actor_id') or '-'})"
            )
            lines.append(
                f"  {entry.get('old_value') or '（空）'} → {entry.get('new_value') or '（空）'}"
            )
        return "\n".join(lines)

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
        """插件卸载/重载时收尾：注销 LLM 工具并断开 WebUI 引用，避免旧实例残留。"""
        for tool_name in (VIEW_TOOL_NAME, REMEMBER_TOOL_NAME, FORGET_TOOL_NAME):
            try:
                self.context.unregister_llm_tool(tool_name)
            except Exception as exc:  # pragma: no cover - 取决于宿主实现
                self._debug(f"注销 LLM 工具 {tool_name} 失败：{exc}")
        self.web_api = None
        self._debug("terminate finished: llm tools unregistered, webui detached")
