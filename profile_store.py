from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

NOTES_FIELD_NAME = "备注"

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
        self.max_notes_count = max(1, min(int(max_notes_count), 20))
        self.custom_field_name_max_length = max(4, min(int(custom_field_name_max_length), 32))
        self.field_value_max_length = max(32, min(int(field_value_max_length), 500))
        self.builtin_field_map = self._build_builtin_field_map(builtin_fields)
        self.profiles = self._load_profiles()

    @staticmethod
    def now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def normalize_field_name(field_name: str) -> str:
        return re.sub(r"\s+", " ", str(field_name or "").strip())

    def _build_builtin_field_map(self, builtin_fields: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_name in builtin_fields:
            field_name = self.normalize_field_name(raw_name)
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

    def _load_profiles(self) -> dict[str, Any]:
        if self.profiles_path.exists():
            raw_profiles = self._read_json(self.profiles_path)
        elif self.legacy_profiles_path.exists():
            raw_profiles = self._migrate_legacy_profiles(self._read_json(self.legacy_profiles_path))
            self._write_json(self.profiles_path, raw_profiles)
        else:
            raw_profiles = {}

        normalized: dict[str, Any] = {}
        for session_key, payload in raw_profiles.items():
            if not isinstance(payload, dict):
                continue
            user_id = str(payload.get("subject_user_id") or self._extract_user_id_from_key(session_key))
            subject_name = str(payload.get("subject_name") or "")
            normalized[session_key] = self._normalize_profile_record(payload, user_id, subject_name)
        return normalized

    def _migrate_legacy_profiles(self, legacy_profiles: dict[str, Any]) -> dict[str, Any]:
        migrated: dict[str, Any] = {}
        for session_key, payload in legacy_profiles.items():
            if not isinstance(payload, dict):
                continue
            user_id = self._extract_user_id_from_key(session_key)
            migrated[session_key] = self._normalize_profile_record(payload, user_id, "")
        return migrated

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
                field_name = self.normalize_field_name(raw_field_name)
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
            field_name = self.normalize_field_name(raw_field_name)
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
            field_name = self.normalize_field_name(raw_field_name)
            if not field_name or not isinstance(raw_metadata, dict):
                continue
            custom_fields[field_name] = {
                "description": str(raw_metadata.get("description") or "").strip(),
                "created_at": str(raw_metadata.get("created_at") or created_at),
                "created_by": str(raw_metadata.get("created_by") or "unknown"),
            }

        field_meta: dict[str, Any] = {}
        for raw_field_name, raw_metadata in field_meta_payload.items():
            field_name = self.normalize_field_name(raw_field_name)
            if not field_name or not isinstance(raw_metadata, dict):
                continue
            field_meta[field_name] = {
                "updated_at": str(raw_metadata.get("updated_at") or updated_at),
                "updated_by": str(raw_metadata.get("updated_by") or "unknown"),
                "source_kind": str(raw_metadata.get("source_kind") or "unknown"),
                "evidence": str(raw_metadata.get("evidence") or "").strip(),
            }

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
        normalized = self.normalize_field_name(field_name)
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
        normalized_field = self.normalize_field_name(field_name)
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

        normalized_selector = self.normalize_field_name(field_selector)
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
