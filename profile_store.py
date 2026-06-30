from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from astrbot.api import logger

NOTES_FIELD_NAME = "备注"
LEGACY_PLUGIN_DIR_NAMES = ("astrbot_plugin_soulmap", "SoulMap", "soulmap")
CANONICAL_FIELD_ALIASES = {
    "称呼": "昵称",
    "对用户的称呼": "昵称",
    "名字": "昵称",
    "姓名": "昵称",
}
PROFILE_NAME_FIELD_NAMES = ("昵称", "对用户的称呼", "称呼", "名字", "姓名", "别名", "网名", "用户名")
PROFILE_NAME_FIELD_NAME_SET = {re.sub(r"\s+", " ", name.strip()) for name in PROFILE_NAME_FIELD_NAMES}
PROFILE_CONFLICT_SPLIT_PATTERN = re.compile(r"[、,，/|;；\n]+")
PROFILE_CONFLICT_STRIP_CHARS = " \t\r\n\"'“”‘’`[]()（）【】<>《》:："

DEFAULT_FIELDS: list[tuple[str, str]] = [
    ("昵称", "用户希望被如何称呼"),
    ("性别", "用户明确表达的性别或性别认同"),
    ("年龄", "相对稳定的年龄信息"),
    ("所在地", "常驻城市、地区或国家"),
    ("生日", "生日或重要纪念日期"),
    ("爱吃", "用户明确表达喜欢吃的东西"),
    ("忌口", "过敏、忌口或不吃的东西"),
    ("爱好", "兴趣爱好"),
    ("职业", "职业、专业或长期身份"),
    ("重要节日", "对用户重要的节日或纪念日"),
    ("恐惧/弱点", "用户主动表达的害怕或不擅长的内容"),
    ("作息规律", "比较稳定的作息偏好"),
    ("技能水平", "用户主动表达的技能或熟练度"),
    ("健康状况", "用户主动披露且适合长期记忆的健康信息"),
    ("宠物", "宠物相关信息"),
    (NOTES_FIELD_NAME, "短期补充备注，会自动保留最近几条"),
]

DEFAULT_FIELD_DESCRIPTIONS = {name: desc for name, desc in DEFAULT_FIELDS}
CUSTOM_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-/\u4e00-\u9fff ]+$")
NOTE_INDEX_PATTERN = re.compile(rf"^(?:{NOTES_FIELD_NAME}\s*[:#])?\s*(\d+)$")
FORBIDDEN_FIELD_FRAGMENTS = (
    "system",
    "prompt",
    "tool",
    "session",
    "message",
    "assistant",
    "bot",
    "系统",
    "提示词",
    "工具",
    "会话",
    "消息",
    "群友",
    "聊天记录",
    "管理员口令",
)
BLOCKED_PROFILE_NAME_VALUES = (
    "爸爸",
    "爹",
    "爹地",
    "义父",
    "主人",
    "master",
    "owner",
    "系统",
    "system",
    "assistant",
    "管理员",
    "群主",
)


@dataclass(slots=True)
class AuditActor:
    actor_type: str
    actor_id: str
    actor_name: str


@dataclass(slots=True)
class OperationResult:
    ok: bool
    message: str
    changed: bool = False
    created_custom_field: bool = False


class ProfileStore:
    def __init__(
        self,
        data_dir: Path,
        builtin_fields: list[str],
        max_notes_count: int = 5,
        custom_field_name_max_length: int = 16,
        field_value_max_length: int = 160,
    ) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_path = self.data_dir / "profiles.json"
        self.audit_log_path = self.data_dir / "audit_log.jsonl"
        self.legacy_profiles_path = self.data_dir / "user_profiles.json"
        self.migration_state_path = self.data_dir / "migration_state.json"
        self.max_notes_count = max(1, min(int(max_notes_count), 20))
        self.custom_field_name_max_length = max(4, min(int(custom_field_name_max_length), 32))
        self.field_value_max_length = max(32, min(int(field_value_max_length), 500))
        self.builtin_field_map = self._build_builtin_field_map(builtin_fields)
        self.migration_state = self._load_migration_state()
        self.profiles = self._load_profiles()

    @staticmethod
    def now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def normalize_field_name(field_name: str) -> str:
        return re.sub(r"\s+", " ", str(field_name or "").strip())

    @classmethod
    def canonical_field_name(cls, field_name: str) -> str:
        normalized = cls.normalize_field_name(field_name)
        return CANONICAL_FIELD_ALIASES.get(normalized, normalized)

    @staticmethod
    def _normalize_conflict_token(value: Any) -> str:
        text = str(value or "").strip(PROFILE_CONFLICT_STRIP_CHARS)
        text = re.sub(r"\s+", "", text)
        return text.casefold()

    def _extract_conflict_tokens(self, raw_value: Any) -> list[tuple[str, str]]:
        if isinstance(raw_value, list):
            source_items = raw_value
        else:
            source_items = PROFILE_CONFLICT_SPLIT_PATTERN.split(str(raw_value or ""))

        tokens: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in source_items:
            display_text = str(item or "").strip(PROFILE_CONFLICT_STRIP_CHARS)
            token = self._normalize_conflict_token(display_text)
            if len(token) < 2 or token in seen:
                continue
            seen.add(token)
            tokens.append((token, display_text))
        return tokens

    def _is_profile_name_field(self, field_name: str) -> bool:
        normalized = self.normalize_field_name(field_name)
        return normalized in PROFILE_NAME_FIELD_NAME_SET

    def _profile_label(self, session_key: str, record: dict[str, Any]) -> str:
        subject_name = str(record.get("subject_name") or "").strip()
        subject_user_id = str(record.get("subject_user_id") or self._extract_user_id_from_key(session_key)).strip()
        if subject_name:
            return f"{subject_name}({subject_user_id})"
        return subject_user_id

    def _iter_profile_name_tokens(self) -> list[tuple[str, str, str, str, str]]:
        matches: list[tuple[str, str, str, str, str]] = []
        for session_key, record in self.profiles.items():
            if not isinstance(record, dict):
                continue
            fields = record.get("fields", {})
            if not isinstance(fields, dict):
                continue
            for field_name, value in fields.items():
                if not self._is_profile_name_field(field_name):
                    continue
                for token, display_text in self._extract_conflict_tokens(value):
                    matches.append((token, display_text, session_key, field_name, self._profile_label(session_key, record)))
        return matches

    def _iter_profile_note_tokens(self) -> list[tuple[str, str, str, str]]:
        matches: list[tuple[str, str, str, str]] = []
        for session_key, record in self.profiles.items():
            if not isinstance(record, dict):
                continue
            fields = record.get("fields", {})
            if not isinstance(fields, dict):
                continue
            for token, display_text in self._extract_conflict_tokens(fields.get(NOTES_FIELD_NAME, [])):
                matches.append((token, display_text, session_key, self._profile_label(session_key, record)))
        return matches

    def _validate_profile_identity_conflicts(
        self,
        *,
        session_key: str,
        record: dict[str, Any],
        field_name: str,
        value: str,
    ) -> OperationResult:
        candidate_tokens = self._extract_conflict_tokens(value)
        if not candidate_tokens:
            return OperationResult(True, "画像身份冲突检查通过")

        normalized_field = self.normalize_field_name(field_name)
        is_name_field = self._is_profile_name_field(normalized_field)

        if is_name_field:
            for token, display_text in candidate_tokens:
                if token in BLOCKED_PROFILE_NAME_VALUES:
                    return OperationResult(
                        False,
                        f"拒绝写入：称呼/名字「{display_text}」属于容易冒犯、诱导或混淆系统身份的称呼。请向用户说明没有写入，并请用户换一个更合适的称呼。",
                    )
                for existing_token, existing_text, existing_key, existing_field, owner_label in self._iter_profile_name_tokens():
                    if token != existing_token:
                        continue
                    if existing_key == session_key and self.normalize_field_name(existing_field) == normalized_field:
                        continue
                    return OperationResult(
                        False,
                        f"拒绝写入：称呼/名字「{display_text}」与 {owner_label} 的「{existing_field}：{existing_text}」重复，可能导致画像混淆。请向用户说明没有写入，并请用户换一个更明确的称呼。",
                    )
                for note_token, note_text, _, owner_label in self._iter_profile_note_tokens():
                    if token != note_token:
                        continue
                    return OperationResult(
                        False,
                        f"拒绝写入：称呼/名字「{display_text}」与 {owner_label} 的备注「{note_text}」重复，名字和备注不能互相复用。请向用户说明没有写入。",
                    )
            return OperationResult(True, "画像身份冲突检查通过")

        if normalized_field == NOTES_FIELD_NAME:
            name_tokens = self._iter_profile_name_tokens()
            for token, display_text in candidate_tokens:
                for name_token, name_text, _, name_field, owner_label in name_tokens:
                    if token != name_token:
                        continue
                    return OperationResult(
                        False,
                        f"拒绝写入：备注「{display_text}」与 {owner_label} 的「{name_field}：{name_text}」重复，名字和备注不能互相复用。请向用户说明没有写入。",
                    )

        return OperationResult(True, "画像身份冲突检查通过")

    def _build_builtin_field_map(self, builtin_fields: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_name in builtin_fields:
            field_name = self.canonical_field_name(raw_name)
            if not field_name:
                continue
            result[field_name] = DEFAULT_FIELD_DESCRIPTIONS.get(field_name, "基础画像字段")
        if NOTES_FIELD_NAME not in result:
            result[NOTES_FIELD_NAME] = DEFAULT_FIELD_DESCRIPTIONS[NOTES_FIELD_NAME]
        return result

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_migration_state(self) -> dict[str, Any]:
        raw_state = self._read_json(self.migration_state_path)
        sources = raw_state.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        return {"sources": sources}

    def _save_migration_state(self) -> None:
        self._write_json(self.migration_state_path, self.migration_state)

    def _normalize_profiles_payload(self, raw_profiles: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for session_key, payload in raw_profiles.items():
            if not isinstance(payload, dict):
                continue
            user_id = str(payload.get("subject_user_id") or self._extract_user_id_from_key(session_key))
            subject_name = str(payload.get("subject_name") or "")
            normalized[session_key] = self._normalize_profile_record(payload, user_id, subject_name)
        return normalized

    def _load_profiles(self) -> dict[str, Any]:
        normalized = self._normalize_profiles_payload(self._read_json(self.profiles_path))
        changed = False

        for legacy_path in self._iter_legacy_profile_sources():
            normalized, imported = self._maybe_import_legacy_source(normalized, legacy_path)
            changed = changed or imported

        if changed or (normalized and not self.profiles_path.exists()):
            self._write_json(self.profiles_path, normalized)
        return normalized

    def _migrate_legacy_profiles(self, legacy_profiles: dict[str, Any]) -> dict[str, Any]:
        migrated: dict[str, Any] = {}
        for session_key, payload in legacy_profiles.items():
            if not isinstance(payload, dict):
                continue
            user_id = self._extract_user_id_from_key(session_key)
            migrated[session_key] = self._normalize_profile_record(payload, user_id, "")
        return migrated

    def _iter_legacy_profile_sources(self) -> list[Path]:
        candidates: list[Path] = [self.legacy_profiles_path]
        plugin_data_root = self.data_dir.parent
        if plugin_data_root.exists():
            for dirname in LEGACY_PLUGIN_DIR_NAMES:
                candidates.append(plugin_data_root / dirname / "user_profiles.json")
            try:
                for sibling in plugin_data_root.iterdir():
                    if not sibling.is_dir():
                        continue
                    if sibling.resolve() == self.data_dir.resolve():
                        continue
                    if "soulmap" in sibling.name.casefold():
                        candidates.append(sibling / "user_profiles.json")
            except OSError:
                pass

        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            signature_key = str(path.resolve(strict=False)).casefold()
            if signature_key in seen:
                continue
            seen.add(signature_key)
            unique_candidates.append(path)
        return unique_candidates

    def _legacy_source_key(self, path: Path) -> str:
        return str(path.resolve(strict=False))

    def _legacy_source_signature(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        resolved = path.resolve(strict=False)
        return f"{resolved}|{stat.st_mtime_ns}|{stat.st_size}"

    def _maybe_import_legacy_source(
        self,
        current_profiles: dict[str, Any],
        legacy_path: Path,
    ) -> tuple[dict[str, Any], bool]:
        source_signature = self._legacy_source_signature(legacy_path)
        if source_signature is None:
            return current_profiles, False

        source_key = self._legacy_source_key(legacy_path)
        previous_state = self.migration_state["sources"].get(source_key, {})
        if previous_state.get("signature") == source_signature:
            return current_profiles, False

        migrated_profiles = self._migrate_legacy_profiles(self._read_json(legacy_path))
        changed = False
        merged_profiles = current_profiles
        status = "empty"
        if migrated_profiles:
            merged_profiles, changed = self._merge_profiles(current_profiles, migrated_profiles)
            status = "merged" if changed else "already_applied"
            if changed:
                logger.info(
                    "[ProfileWeaver] Imported %s legacy profile records from %s",
                    len(migrated_profiles),
                    legacy_path,
                )
        else:
            logger.warning("[ProfileWeaver] Legacy profile source %s is empty or unreadable", legacy_path)

        self.migration_state["sources"][source_key] = {
            "signature": source_signature,
            "source_path": str(legacy_path.resolve(strict=False)),
            "record_count": len(migrated_profiles),
            "status": status,
            "imported_at": self.now_text(),
        }
        self._save_migration_state()
        return merged_profiles, changed

    @staticmethod
    def _coerce_timestamp(raw_value: Any) -> str:
        text = str(raw_value or "").strip()
        return text

    def _pick_latest_timestamp(self, *values: Any) -> str:
        timestamps = []
        for value in values:
            text = self._coerce_timestamp(value)
            if text:
                timestamps.append(text)
        return max(timestamps) if timestamps else self.now_text()

    def _pick_earliest_timestamp(self, *values: Any) -> str:
        timestamps = []
        for value in values:
            text = self._coerce_timestamp(value)
            if text:
                timestamps.append(text)
        return min(timestamps) if timestamps else self.now_text()

    def _normalize_field_meta_entry(
        self,
        raw_metadata: Any,
        fallback_updated_at: str,
    ) -> dict[str, Any]:
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        return {
            "updated_at": str(raw_metadata.get("updated_at") or fallback_updated_at),
            "updated_by": str(raw_metadata.get("updated_by") or "unknown"),
            "actor_id": str(raw_metadata.get("actor_id") or ""),
            "actor_name": str(raw_metadata.get("actor_name") or ""),
            "source_kind": str(raw_metadata.get("source_kind") or "unknown"),
            "evidence": str(raw_metadata.get("evidence") or "").strip(),
        }

    def _merge_custom_field_meta(
        self,
        current_meta: Any,
        incoming_meta: Any,
    ) -> dict[str, Any]:
        if not isinstance(current_meta, dict):
            current_meta = {}
        if not isinstance(incoming_meta, dict):
            incoming_meta = {}

        current_created_at = self._coerce_timestamp(current_meta.get("created_at"))
        incoming_created_at = self._coerce_timestamp(incoming_meta.get("created_at"))
        prefer_incoming = bool(incoming_created_at and incoming_created_at >= current_created_at)
        description = str(current_meta.get("description") or "").strip()
        if prefer_incoming and str(incoming_meta.get("description") or "").strip():
            description = str(incoming_meta.get("description") or "").strip()
        elif not description:
            description = str(incoming_meta.get("description") or "").strip()

        created_by = str(current_meta.get("created_by") or "").strip()
        if prefer_incoming and str(incoming_meta.get("created_by") or "").strip():
            created_by = str(incoming_meta.get("created_by") or "").strip()
        elif not created_by:
            created_by = str(incoming_meta.get("created_by") or "unknown").strip()

        return {
            "description": description,
            "created_at": self._pick_earliest_timestamp(
                current_meta.get("created_at"),
                incoming_meta.get("created_at"),
            ),
            "created_by": created_by or "unknown",
        }

    def _merge_field_meta_entry(
        self,
        current_meta: Any,
        incoming_meta: Any,
        fallback_updated_at: str,
    ) -> dict[str, Any]:
        normalized_current = self._normalize_field_meta_entry(current_meta, fallback_updated_at)
        normalized_incoming = self._normalize_field_meta_entry(incoming_meta, fallback_updated_at)
        current_updated_at = normalized_current["updated_at"]
        incoming_updated_at = normalized_incoming["updated_at"]
        if incoming_updated_at >= current_updated_at:
            return normalized_incoming
        return normalized_current

    def _merge_note_values(
        self,
        current_value: Any,
        incoming_value: Any,
        *,
        prefer_incoming_tail: bool,
    ) -> list[str]:
        current_notes = self._normalize_notes(current_value)
        incoming_notes = self._normalize_notes(incoming_value)
        if prefer_incoming_tail:
            return self._normalize_notes([*current_notes, *incoming_notes])
        return self._normalize_notes([*incoming_notes, *current_notes])

    def _merge_profile_record(
        self,
        current_record: dict[str, Any],
        incoming_record: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        merged = json.loads(json.dumps(current_record, ensure_ascii=False))
        changed = False

        merged["subject_user_id"] = str(
            merged.get("subject_user_id") or incoming_record.get("subject_user_id") or ""
        )
        if not str(merged.get("subject_name") or "").strip() and str(incoming_record.get("subject_name") or "").strip():
            merged["subject_name"] = str(incoming_record.get("subject_name") or "").strip()
            changed = True

        merged_created_at = self._pick_earliest_timestamp(
            merged.get("created_at"),
            incoming_record.get("created_at"),
        )
        if merged.get("created_at") != merged_created_at:
            merged["created_at"] = merged_created_at
            changed = True

        merged_fields = merged.setdefault("fields", {})
        merged_custom_fields = merged.setdefault("custom_fields", {})
        merged_field_meta = merged.setdefault("field_meta", {})
        incoming_fields = incoming_record.get("fields", {})
        incoming_custom_fields = incoming_record.get("custom_fields", {})
        incoming_field_meta = incoming_record.get("field_meta", {})

        for field_name, incoming_value in incoming_fields.items():
            current_value = merged_fields.get(field_name)
            current_meta = merged_field_meta.get(field_name, {})
            incoming_meta = incoming_field_meta.get(field_name, {})
            current_field_updated_at = self._pick_latest_timestamp(
                (current_meta or {}).get("updated_at") if isinstance(current_meta, dict) else "",
                current_record.get("updated_at"),
            )
            incoming_field_updated_at = self._pick_latest_timestamp(
                (incoming_meta or {}).get("updated_at") if isinstance(incoming_meta, dict) else "",
                incoming_record.get("updated_at"),
            )
            normalized_meta = self._merge_field_meta_entry(
                current_meta,
                incoming_meta,
                fallback_updated_at=self._pick_latest_timestamp(current_field_updated_at, incoming_field_updated_at),
            )
            incoming_is_newer = incoming_field_updated_at >= current_field_updated_at

            if field_name == NOTES_FIELD_NAME:
                merged_value = self._merge_note_values(
                    current_value,
                    incoming_value,
                    prefer_incoming_tail=incoming_is_newer,
                )
            elif current_value is None or incoming_is_newer:
                merged_value = incoming_value
            else:
                merged_value = current_value

            if merged_value != current_value:
                merged_fields[field_name] = merged_value
                changed = True
            if merged_field_meta.get(field_name) != normalized_meta:
                merged_field_meta[field_name] = normalized_meta
                changed = True

        for field_name, incoming_meta in incoming_custom_fields.items():
            merged_meta = self._merge_custom_field_meta(merged_custom_fields.get(field_name), incoming_meta)
            if merged_custom_fields.get(field_name) != merged_meta:
                merged_custom_fields[field_name] = merged_meta
                changed = True

        merged_updated_at = self._pick_latest_timestamp(
            merged.get("updated_at"),
            incoming_record.get("updated_at"),
            *[
                metadata.get("updated_at")
                for metadata in merged_field_meta.values()
                if isinstance(metadata, dict)
            ],
        )
        if merged.get("updated_at") != merged_updated_at:
            merged["updated_at"] = merged_updated_at
            changed = True
        return merged, changed

    def _merge_profiles(
        self,
        current_profiles: dict[str, Any],
        incoming_profiles: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        merged = json.loads(json.dumps(current_profiles, ensure_ascii=False))
        changed = False
        for session_key, incoming_record in incoming_profiles.items():
            current_record = merged.get(session_key)
            if not isinstance(current_record, dict):
                merged[session_key] = incoming_record
                changed = True
                continue
            merged_record, record_changed = self._merge_profile_record(current_record, incoming_record)
            if record_changed:
                merged[session_key] = merged_record
                changed = True
        return merged, changed

    @staticmethod
    def _extract_user_id_from_key(session_key: str) -> str:
        if "_" not in session_key:
            return session_key
        return session_key.rsplit("_", 1)[-1]

    def _normalize_notes(self, raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            source_items = raw_value
        else:
            source_items = re.split(r"[；;\n]+", str(raw_value or ""))
        notes: list[str] = []
        for item in source_items:
            text = str(item or "").strip()
            if not text:
                continue
            if text not in notes:
                notes.append(text[: self.field_value_max_length])
        return notes[-self.max_notes_count :]

    def _normalize_profile_record(
        self,
        payload: dict[str, Any],
        subject_user_id: str,
        subject_name: str,
    ) -> dict[str, Any]:
        if "fields" not in payload:
            updated_at = str(payload.get("_last_updated") or self.now_text())
            fields: dict[str, Any] = {}
            custom_fields: dict[str, Any] = {}
            field_meta: dict[str, Any] = {}
            for raw_field_name, raw_value in payload.items():
                if str(raw_field_name).startswith("_"):
                    continue
                field_name = self.canonical_field_name(raw_field_name)
                if not field_name:
                    continue
                if field_name == NOTES_FIELD_NAME:
                    notes = self._normalize_notes(raw_value)
                    if notes:
                        fields[field_name] = notes
                else:
                    value_text = str(raw_value or "").strip()
                    if value_text:
                        fields[field_name] = value_text[: self.field_value_max_length]
                if field_name not in fields:
                    continue
                if field_name not in self.builtin_field_map:
                    custom_fields[field_name] = {
                        "description": "从上游 SoulMap 迁移的自定义字段",
                        "created_at": updated_at,
                        "created_by": "migration",
                    }
                field_meta[field_name] = {
                    "updated_at": updated_at,
                    "updated_by": "migration",
                    "source_kind": "migration",
                    "evidence": "",
                }
            return {
                "subject_user_id": subject_user_id,
                "subject_name": subject_name,
                "created_at": updated_at,
                "updated_at": updated_at,
                "fields": fields,
                "custom_fields": custom_fields,
                "field_meta": field_meta,
            }

        created_at = str(payload.get("created_at") or self.now_text())
        updated_at = str(payload.get("updated_at") or created_at)
        fields_payload = payload.get("fields", {})
        custom_fields_payload = payload.get("custom_fields", {})
        field_meta_payload = payload.get("field_meta", {})

        fields: dict[str, Any] = {}
        for raw_field_name, raw_value in fields_payload.items():
            field_name = self.canonical_field_name(raw_field_name)
            if not field_name:
                continue
            if field_name == NOTES_FIELD_NAME:
                notes = self._normalize_notes(raw_value)
                if notes:
                    fields[field_name] = notes
            else:
                text = str(raw_value or "").strip()
                if text:
                    fields[field_name] = text[: self.field_value_max_length]

        custom_fields: dict[str, Any] = {}
        for raw_field_name, raw_metadata in custom_fields_payload.items():
            field_name = self.canonical_field_name(raw_field_name)
            if not field_name or not isinstance(raw_metadata, dict):
                continue
            if field_name in self.builtin_field_map:
                continue
            custom_fields[field_name] = {
                "description": str(raw_metadata.get("description") or "").strip(),
                "created_at": str(raw_metadata.get("created_at") or created_at),
                "created_by": str(raw_metadata.get("created_by") or "unknown"),
            }

        field_meta: dict[str, Any] = {}
        for raw_field_name, raw_metadata in field_meta_payload.items():
            field_name = self.canonical_field_name(raw_field_name)
            if not field_name or not isinstance(raw_metadata, dict):
                continue
            field_meta[field_name] = self._normalize_field_meta_entry(raw_metadata, updated_at)

        return {
            "subject_user_id": subject_user_id,
            "subject_name": subject_name,
            "created_at": created_at,
            "updated_at": updated_at,
            "fields": fields,
            "custom_fields": custom_fields,
            "field_meta": field_meta,
        }

    def _profile_key(self, user_id: str, session_id: str | None = None) -> str:
        return f"{session_id}_{user_id}" if session_id else user_id

    def _save_profiles(self) -> None:
        self._write_json(self.profiles_path, self.profiles)

    def _ensure_profile(
        self,
        user_id: str,
        subject_name: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        session_key = self._profile_key(user_id, session_id)
        if session_key not in self.profiles:
            now = self.now_text()
            self.profiles[session_key] = {
                "subject_user_id": user_id,
                "subject_name": subject_name,
                "created_at": now,
                "updated_at": now,
                "fields": {},
                "custom_fields": {},
                "field_meta": {},
            }
        record = self.profiles[session_key]
        if subject_name:
            record["subject_name"] = subject_name
        return record

    def get_profile(self, user_id: str, session_id: str | None = None) -> dict[str, Any]:
        session_key = self._profile_key(user_id, session_id)
        record = self.profiles.get(session_key)
        if record is None:
            return {}
        return json.loads(json.dumps(record, ensure_ascii=False))

    def get_last_updated(self, user_id: str, session_id: str | None = None) -> str | None:
        profile = self.get_profile(user_id, session_id)
        return str(profile.get("updated_at")) if profile else None

    def list_field_definitions(
        self,
        user_id: str,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        profile = self.get_profile(user_id, session_id)
        custom_fields = profile.get("custom_fields", {}) if profile else {}
        field_defs: list[dict[str, Any]] = []
        for field_name, description in self.builtin_field_map.items():
            field_defs.append(
                {
                    "name": field_name,
                    "description": description,
                    "is_custom": False,
                }
            )
        for field_name, metadata in custom_fields.items():
            field_defs.append(
                {
                    "name": field_name,
                    "description": str(metadata.get("description") or "当前用户的自定义字段"),
                    "is_custom": True,
                }
            )
        return field_defs

    def format_field_catalog(self, user_id: str, session_id: str | None = None) -> str:
        definitions = self.list_field_definitions(user_id, session_id)
        if not definitions:
            return "暂无字段"
        lines = []
        for item in definitions:
            field_name = item["name"]
            field_desc = item["description"]
            if item["is_custom"]:
                lines.append(f"- {field_name}：{field_desc}（当前用户自定义字段）")
            else:
                lines.append(f"- {field_name}：{field_desc}")
        return "\n".join(lines)

    def format_custom_field_catalog(self, user_id: str, session_id: str | None = None) -> str:
        profile = self.get_profile(user_id, session_id)
        if not profile:
            return "无"
        custom_fields = profile.get("custom_fields", {})
        if not custom_fields:
            return "无"
        lines = []
        for field_name, metadata in custom_fields.items():
            desc = str(metadata.get("description") or "当前用户自定义字段")
            lines.append(f"- {field_name}：{desc}")
        return "\n".join(lines)

    def format_profile_summary(self, user_id: str, session_id: str | None = None) -> str:
        profile = self.get_profile(user_id, session_id)
        if not profile:
            return "暂无记录"

        fields = profile.get("fields", {})
        if not fields:
            return "暂无记录"

        lines: list[str] = []
        for field_name in self.builtin_field_map:
            if field_name not in fields:
                continue
            value = fields[field_name]
            if field_name == NOTES_FIELD_NAME and isinstance(value, list):
                notes_text = " ".join(f"{idx}.{note}" for idx, note in enumerate(value, start=1))
                lines.append(f"- {field_name}：{notes_text}")
            else:
                lines.append(f"- {field_name}：{value}")

        custom_fields = profile.get("custom_fields", {})
        for field_name in custom_fields:
            if field_name not in fields:
                continue
            lines.append(f"- {field_name}：{fields[field_name]}")

        return "\n".join(lines) if lines else "暂无记录"

    def is_known_field(self, user_id: str, field_name: str, session_id: str | None = None) -> bool:
        normalized = self.canonical_field_name(field_name)
        if normalized in self.builtin_field_map:
            return True
        profile = self.get_profile(user_id, session_id)
        custom_fields = profile.get("custom_fields", {})
        return normalized in custom_fields

    def validate_custom_field_name(self, field_name: str) -> OperationResult:
        normalized = self.normalize_field_name(field_name)
        if not normalized:
            return OperationResult(False, "字段名不能为空")
        if len(normalized) > self.custom_field_name_max_length:
            return OperationResult(
                False,
                f"字段名过长，最多 {self.custom_field_name_max_length} 个字符",
            )
        if not CUSTOM_FIELD_NAME_PATTERN.fullmatch(normalized):
            return OperationResult(False, "字段名只能包含中文、字母、数字、空格、_、-、/")
        lowered = normalized.casefold()
        if any(fragment in lowered for fragment in FORBIDDEN_FIELD_FRAGMENTS):
            return OperationResult(False, "字段名涉及系统或敏感语义，已拒绝创建")
        return OperationResult(True, "字段名可用")

    def _touch_field_meta(
        self,
        record: dict[str, Any],
        field_name: str,
        actor: AuditActor,
        source_kind: str,
        evidence: str,
    ) -> None:
        record["field_meta"][field_name] = {
            "updated_at": self.now_text(),
            "updated_by": actor.actor_type,
            "actor_id": actor.actor_id,
            "actor_name": actor.actor_name,
            "source_kind": source_kind,
            "evidence": evidence[:160],
        }

    def _append_audit(
        self,
        *,
        action: str,
        user_id: str,
        subject_name: str,
        session_id: str | None,
        actor: AuditActor,
        field_name: str,
        source_kind: str,
        evidence: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        entry = {
            "at": self.now_text(),
            "session_id": session_id or "",
            "subject_user_id": user_id,
            "subject_name": subject_name,
            "actor_type": actor.actor_type,
            "actor_id": actor.actor_id,
            "actor_name": actor.actor_name,
            "action": action,
            "field_name": field_name,
            "source_kind": source_kind,
            "evidence": evidence[:160],
            "old_value": self._compact_value(old_value),
            "new_value": self._compact_value(new_value),
        }
        with self.audit_log_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _compact_value(self, value: Any) -> str:
        if isinstance(value, list):
            text = " | ".join(str(item) for item in value)
        else:
            text = str(value or "")
        return text[:200]

    def upsert_field(
        self,
        *,
        user_id: str,
        subject_name: str,
        field_name: str,
        value: str,
        session_id: str | None,
        actor: AuditActor,
        source_kind: str,
        evidence: str,
        allow_custom_field: bool,
        field_description: str = "",
    ) -> OperationResult:
        normalized_field = self.canonical_field_name(field_name)
        value_text = str(value or "").strip()
        if not normalized_field:
            return OperationResult(False, "字段名不能为空")
        if not value_text:
            return OperationResult(False, "字段值不能为空")
        value_text = value_text[: self.field_value_max_length]

        record = self._ensure_profile(user_id, subject_name, session_id)
        fields = record["fields"]
        custom_fields = record["custom_fields"]
        created_custom_field = False
        session_key = self._profile_key(user_id, session_id)

        if normalized_field not in self.builtin_field_map and normalized_field not in custom_fields:
            if not allow_custom_field:
                return OperationResult(
                    False,
                    "字段不存在。若确实需要新字段，请显式允许创建当前用户自定义字段。",
                )
            validation = self.validate_custom_field_name(normalized_field)
            if not validation.ok:
                return validation
            custom_fields[normalized_field] = {
                "description": str(field_description or "当前用户自定义字段").strip()[:80],
                "created_at": self.now_text(),
                "created_by": actor.actor_type,
            }
            created_custom_field = True

        conflict_validation = self._validate_profile_identity_conflicts(
            session_key=session_key,
            record=record,
            field_name=normalized_field,
            value=value_text,
        )
        if not conflict_validation.ok:
            if created_custom_field:
                custom_fields.pop(normalized_field, None)
            return conflict_validation

        old_value = fields.get(normalized_field)
        if normalized_field == NOTES_FIELD_NAME:
            merged_notes = self._normalize_notes([*(old_value or []), *self._normalize_notes(value_text)])
            if merged_notes == old_value:
                return OperationResult(True, "备注没有新的变化")
            fields[normalized_field] = merged_notes
            new_value: Any = merged_notes
            audit_action = "append_note"
        else:
            if old_value == value_text:
                return OperationResult(True, f"{normalized_field} 已经是最新值")
            fields[normalized_field] = value_text
            new_value = value_text
            audit_action = "upsert_field"

        record["updated_at"] = self.now_text()
        self._touch_field_meta(record, normalized_field, actor, source_kind, evidence)
        self._save_profiles()
        self._append_audit(
            action=audit_action,
            user_id=user_id,
            subject_name=record["subject_name"],
            session_id=session_id,
            actor=actor,
            field_name=normalized_field,
            source_kind=source_kind,
            evidence=evidence,
            old_value=old_value,
            new_value=new_value,
        )
        if created_custom_field:
            return OperationResult(True, f"已写入 {normalized_field}，并创建当前用户自定义字段", True, True)
        return OperationResult(True, f"已写入 {normalized_field}", True)

    def delete_field(
        self,
        *,
        user_id: str,
        session_id: str | None,
        field_selector: str,
        actor: AuditActor,
        source_kind: str,
        evidence: str,
    ) -> OperationResult:
        session_key = self._profile_key(user_id, session_id)
        record = self.profiles.get(session_key)
        if not record:
            return OperationResult(False, "没有找到对应画像")

        normalized_selector = self.canonical_field_name(field_selector)
        notes = record["fields"].get(NOTES_FIELD_NAME, [])
        note_match = NOTE_INDEX_PATTERN.fullmatch(normalized_selector)
        if note_match and isinstance(notes, list) and notes:
            note_index = int(note_match.group(1)) - 1
            if note_index < 0 or note_index >= len(notes):
                return OperationResult(False, "备注序号不存在")
            old_notes = list(notes)
            deleted_note = notes.pop(note_index)
            if notes:
                record["fields"][NOTES_FIELD_NAME] = notes
            else:
                record["fields"].pop(NOTES_FIELD_NAME, None)
                record["field_meta"].pop(NOTES_FIELD_NAME, None)
            record["updated_at"] = self.now_text()
            self._save_profiles()
            self._append_audit(
                action="delete_note",
                user_id=user_id,
                subject_name=record["subject_name"],
                session_id=session_id,
                actor=actor,
                field_name=f"{NOTES_FIELD_NAME}:{note_index + 1}",
                source_kind=source_kind,
                evidence=evidence,
                old_value=old_notes,
                new_value=notes,
            )
            self._drop_profile_if_empty(session_key)
            return OperationResult(True, f"已删除备注 {note_index + 1}：{deleted_note}", True)

        fields = record["fields"]
        if normalized_selector not in fields:
            return OperationResult(False, f"未找到字段 {normalized_selector}")

        old_value = fields.pop(normalized_selector)
        record["field_meta"].pop(normalized_selector, None)
        record["custom_fields"].pop(normalized_selector, None)
        record["updated_at"] = self.now_text()
        self._save_profiles()
        self._append_audit(
            action="delete_field",
            user_id=user_id,
            subject_name=record["subject_name"],
            session_id=session_id,
            actor=actor,
            field_name=normalized_selector,
            source_kind=source_kind,
            evidence=evidence,
            old_value=old_value,
            new_value="",
        )
        self._drop_profile_if_empty(session_key)
        return OperationResult(True, f"已删除字段 {normalized_selector}", True)

    def _drop_profile_if_empty(self, session_key: str) -> None:
        record = self.profiles.get(session_key)
        if record is None:
            return
        if record.get("fields"):
            return
        self.profiles.pop(session_key, None)
        self._save_profiles()

    def clear_profile(
        self,
        *,
        user_id: str,
        session_id: str | None,
        actor: AuditActor,
    ) -> OperationResult:
        session_key = self._profile_key(user_id, session_id)
        record = self.profiles.get(session_key)
        if record is None:
            return OperationResult(False, "没有可清空的画像")
        old_value = record.get("fields", {})
        subject_name = str(record.get("subject_name") or "")
        self.profiles.pop(session_key, None)
        self._save_profiles()
        self._append_audit(
            action="clear_profile",
            user_id=user_id,
            subject_name=subject_name,
            session_id=session_id,
            actor=actor,
            field_name="*",
            source_kind="manual_clear",
            evidence="",
            old_value=old_value,
            new_value="",
        )
        return OperationResult(True, "已清空画像", True)

    def collect_stats(self) -> dict[str, Any]:
        user_count = len(self.profiles)
        field_counts: dict[str, int] = {}
        custom_field_counts: dict[str, int] = {}
        for record in self.profiles.values():
            fields = record.get("fields", {})
            custom_fields = record.get("custom_fields", {})
            for field_name in fields:
                field_counts[field_name] = field_counts.get(field_name, 0) + 1
                if field_name in custom_fields:
                    custom_field_counts[field_name] = custom_field_counts.get(field_name, 0) + 1
        return {
            "user_count": user_count,
            "field_counts": field_counts,
            "custom_field_counts": custom_field_counts,
        }

    def read_recent_audit(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not self.audit_log_path.exists():
            return []
        matched = deque(maxlen=max(1, min(int(limit), 50)))
        with self.audit_log_path.open("r", encoding="utf-8") as audit_file:
            for line in audit_file:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if user_id and str(entry.get("subject_user_id")) != user_id:
                    continue
                if session_id is not None and str(entry.get("session_id") or "") != str(session_id or ""):
                    continue
                matched.append(entry)
        return list(reversed(matched))
