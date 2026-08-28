"""Dashboard Web API layer for the 心迹画像 (ProfileWeaver) plugin.

All endpoints are registered under ``/<PLUGIN_NAME>/<endpoint>`` so that the
AstrBot Dashboard bridge (``/api/plug/<plugin_name>/<endpoint>``) can reach them.

Security note: these endpoints inherit the Dashboard authentication state only.
The plugin performs no extra credential check, so the Dashboard must never be
exposed to the public internet.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from quart import Response, jsonify, request

from astrbot.api import logger

try:
    from .profile_store import AuditActor, ProfileStore
except ImportError:  # pragma: no cover - direct module execution fallback
    from profile_store import AuditActor, ProfileStore

PLUGIN_NAME = "astrbot_plugin_profile_weaver"
MAX_UPLOAD_BYTES = 16 * 1024 * 1024

THEMES: list[dict[str, str]] = [
    {"id": "aurora", "name": "极光", "accent": "#3ddc97"},
    {"id": "midnight", "name": "午夜", "accent": "#6c8cff"},
    {"id": "sakura", "name": "樱绯", "accent": "#ff8fab"},
    {"id": "bamboo", "name": "竹青", "accent": "#7bd88f"},
    {"id": "amber", "name": "琥珀", "accent": "#ffb454"},
    {"id": "graphite", "name": "石墨", "accent": "#9aa4b2"},
    {"id": "paper", "name": "素白", "accent": "#2f6f5e"},
]


def _ok(payload: dict[str, Any] | None = None, **extra: Any) -> Response:
    body: dict[str, Any] = {"ok": True}
    if payload:
        body.update(payload)
    if extra:
        body.update(extra)
    return jsonify(body)


def _fail(message: str, status: int = 400) -> Response:
    response = jsonify({"ok": False, "message": message})
    response.status_code = status
    return response


def _as_int(raw: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _as_bool(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class ProfileWebApi:
    """Bundles every Dashboard endpoint used by the ``profiles`` plugin page."""

    ROUTES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("meta", "api_meta", ("GET",)),
        ("stats", "api_stats", ("GET",)),
        ("profiles", "api_profiles", ("GET",)),
        ("profile", "api_profile", ("GET",)),
        ("profile-field", "api_profile_field_upsert", ("POST",)),
        ("profile-field-delete", "api_profile_field_delete", ("POST",)),
        ("profile-delete", "api_profile_delete", ("POST",)),
        ("profile-merge", "api_profile_merge", ("POST",)),
        ("audit", "api_audit", ("GET",)),
        ("export", "api_export", ("GET",)),
        ("import", "api_import", ("POST",)),
        ("backups", "api_backups", ("GET",)),
        ("backup-create", "api_backup_create", ("POST",)),
        ("backup-restore", "api_backup_restore", ("POST",)),
    )

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

    # ---------------------------------------------------------------- helpers
    @property
    def store(self) -> ProfileStore:
        return self.plugin.store

    def register(self, context: Any) -> int:
        registered = 0
        for endpoint, handler_name, methods in self.ROUTES:
            handler: Callable[..., Any] | None = getattr(self, handler_name, None)
            if handler is None:  # pragma: no cover - defensive
                continue
            try:
                context.register_web_api(
                    f"/{PLUGIN_NAME}/{endpoint}",
                    handler,
                    list(methods),
                    f"ProfileWeaver WebUI: {endpoint}",
                )
                registered += 1
            except Exception as exc:  # pragma: no cover - host dependent
                logger.warning(f"[ProfileWeaver] 注册 Web API 失败 {endpoint}: {exc}")
        return registered

    def _allow_edit(self) -> bool:
        return bool(self.plugin.config.get("webui_allow_edit", True))

    def _actor(self) -> AuditActor:
        return AuditActor(actor_type="webui", actor_id="dashboard", actor_name="Dashboard")

    async def _body(self) -> dict[str, Any]:
        try:
            payload = await request.get_json(force=True, silent=True)
        except Exception:  # pragma: no cover - quart version differences
            payload = None
        if isinstance(payload, dict):
            return payload
        try:
            form = await request.form
        except Exception:  # pragma: no cover
            return {}
        return {key: form[key] for key in form.keys()}

    # ------------------------------------------------------------------ reads
    async def api_meta(self) -> Response:
        store = self.store
        builtin_fields = [
            {"name": name, "description": description}
            for name, description in store.builtin_field_map.items()
        ]
        return _ok(
            {
                "plugin": PLUGIN_NAME,
                "display_name": self.plugin.DISPLAY_NAME,
                "subtitle": self.plugin.SUBTITLE,
                "version": self.plugin.VERSION,
                "repo": "https://github.com/Whereis-Alice/astrbot_plugin_profile_weaver",
                "allow_edit": self._allow_edit(),
                "session_based": bool(self.plugin.session_based),
                "llm_tools_enabled": bool(self.plugin.config.get("llm_tools_enabled", True)),
                "proactive_extraction": bool(
                    self.plugin.config.get("proactive_extraction_enabled", True)
                ),
                "llm_write_denylist": self.plugin.llm_write_denylist(),
                "evidence_match_mode": str(
                    self.plugin.config.get("evidence_match_mode", "normalized")
                ),
                "allow_llm_custom_fields": bool(
                    self.plugin.config.get("allow_llm_custom_fields", True)
                ),
                "allow_user_custom_fields": bool(
                    self.plugin.config.get("allow_user_custom_fields", True)
                ),
                "strict_identity_guard": bool(
                    self.plugin.config.get("strict_identity_guard", True)
                ),
                "allow_profile_in_group": bool(
                    self.plugin.config.get("allow_profile_in_group", True)
                ),
                "custom_field_name_max_length": int(
                    self.plugin.config.get("custom_field_name_max_length", 16)
                ),
                "audit_log_max_mb": float(self.plugin.config.get("audit_log_max_mb", 8.0)),
                "backup_retention_days": int(
                    self.plugin.config.get("backup_retention_days", 14)
                ),
                "default_theme": str(self.plugin.config.get("webui_default_theme", "aurora")),
                "export_mask_default": _as_bool(
                    self.plugin.config.get("export_mask_user_ids", False)
                ),
                "max_notes_count": int(self.plugin.config.get("max_notes_count", 5)),
                "field_value_max_length": int(
                    self.plugin.config.get("field_value_max_length", 160)
                ),
                "themes": THEMES,
                "builtin_fields": builtin_fields,
                "platforms": store.list_platforms(),
                "audit_actions": store.audit_action_catalog(),
                "bundle_format": store.BUNDLE_FORMAT,
                "bundle_version": store.BUNDLE_VERSION,
                "commands": self.plugin.command_catalog(),
                "server_time": store.now_text(),
            }
        )

    async def api_stats(self) -> Response:
        store = self.store
        stats = store.collect_stats()
        profile_count = int(stats.get("profile_count") or 0)
        divisor = max(1, profile_count)
        coverage = []
        for name in store.builtin_field_map:
            count = int(stats.get("field_counts", {}).get(name, 0))
            coverage.append(
                {
                    "name": name,
                    "count": count,
                    "ratio": round(count / divisor * 100, 1) if profile_count else 0.0,
                }
            )
        coverage.sort(key=lambda item: (-item["count"], item["name"]))
        custom = [
            {"name": name, "count": int(count)}
            for name, count in sorted(
                stats.get("custom_field_counts", {}).items(),
                key=lambda item: (-int(item[1]), item[0]),
            )
        ]
        return _ok({"stats": stats, "coverage": coverage, "custom_fields": custom})

    async def api_profiles(self) -> Response:
        args = request.args
        result = self.store.list_profiles(
            query=str(args.get("query", "")),
            chat_type=str(args.get("chat_type", "all")),
            platform=str(args.get("platform", "all")),
            field=str(args.get("field", "")),
            sort=str(args.get("sort", "updated_desc")),
            page=_as_int(args.get("page"), 1, 1, 100000),
            page_size=_as_int(args.get("page_size"), 20, 1, 200),
        )
        return _ok(result)

    async def api_profile(self) -> Response:
        key = str(request.args.get("key", "")).strip()
        if not key:
            return _fail("缺少 key 参数")
        detail = self.store.get_profile_detail(key)
        if not detail:
            return _fail("画像不存在或已被删除", 404)
        return _ok({"profile": detail})

    async def api_audit(self) -> Response:
        args = request.args
        result = self.store.read_audit(
            user_id=str(args.get("user_id", "")),
            action=str(args.get("action", "")),
            actor_type=str(args.get("actor_type", "")),
            query=str(args.get("query", "")),
            limit=_as_int(args.get("limit"), 50, 1, 500),
            offset=_as_int(args.get("offset"), 0, 0, 1000000),
        )
        return _ok(result)

    async def api_backups(self) -> Response:
        return _ok({"items": self.store.list_backups()})

    # ----------------------------------------------------------------- writes
    async def api_profile_field_upsert(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式，请在插件配置中开启「WebUI 是否允许写操作」", 403)
        body = await self._body()
        key = str(body.get("key", "")).strip()
        field_name = str(body.get("field", "")).strip()
        value = str(body.get("value", ""))
        if not key or not field_name:
            return _fail("key 与 field 不能为空")

        detail = self.store.get_profile_detail(key)
        if not detail:
            return _fail("画像不存在或已被删除", 404)

        result = self.store.upsert_field(
            user_id=detail["user_id"],
            subject_name=detail.get("subject_name") or detail["user_id"],
            field_name=field_name,
            value=value,
            session_id=detail.get("session_id") or None,
            actor=self._actor(),
            source_kind="webui_edit",
            evidence="Dashboard WebUI 手动编辑",
            allow_custom_field=_as_bool(body.get("allow_custom_field"), True),
            field_description=str(body.get("description", "")) or "通过 WebUI 创建的自定义字段",
        )
        return _ok(
            {
                "ok": result.ok,
                "message": result.message,
                "changed": result.changed,
                "created_custom_field": result.created_custom_field,
                "profile": self.store.get_profile_detail(key),
            }
        )

    async def api_profile_field_delete(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)
        body = await self._body()
        key = str(body.get("key", "")).strip()
        selector = str(body.get("field", "")).strip()
        if not key or not selector:
            return _fail("key 与 field 不能为空")
        detail = self.store.get_profile_detail(key)
        if not detail:
            return _fail("画像不存在或已被删除", 404)
        result = self.store.delete_field(
            user_id=detail["user_id"],
            session_id=detail.get("session_id") or None,
            field_selector=selector,
            actor=self._actor(),
            source_kind="webui_delete",
            evidence="Dashboard WebUI 手动删除",
        )
        return _ok(
            {
                "ok": result.ok,
                "message": result.message,
                "profile": self.store.get_profile_detail(key),
            }
        )

    async def api_profile_delete(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)
        body = await self._body()
        keys = body.get("keys")
        if not isinstance(keys, list) or not keys:
            single = str(body.get("key", "")).strip()
            keys = [single] if single else []
        if not keys:
            return _fail("缺少 key 参数")

        messages: list[str] = []
        removed = 0
        for raw_key in keys[:200]:
            result = self.store.delete_profile_by_key(str(raw_key), self._actor())
            if result.ok:
                removed += 1
            else:
                messages.append(result.message)
        detail_text = "；".join(messages[:3]) if messages else ""
        return _ok({"removed": removed, "message": f"已删除 {removed} 条画像。{detail_text}"})

    async def api_profile_merge(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)
        body = await self._body()
        source_key = str(body.get("source", "")).strip()
        target_key = str(body.get("target", "")).strip()
        if not source_key or not target_key:
            return _fail("source 与 target 不能为空")
        result = self.store.merge_profile_records(
            source_key=source_key,
            target_key=target_key,
            actor=self._actor(),
            drop_source=_as_bool(body.get("drop_source"), True),
        )
        return _ok({"ok": result.ok, "message": result.message})

    async def api_backup_create(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)
        body = await self._body()
        path = self.store.create_backup(str(body.get("tag", "manual")) or "manual")
        if path is None:
            return _fail("备份失败，请检查数据目录写入权限")
        return _ok(
            {
                "name": path.name,
                "message": f"已创建备份 {path.name}",
                "items": self.store.list_backups(),
            }
        )

    async def api_backup_restore(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)
        body = await self._body()
        name = str(body.get("name", "")).strip()
        if not name:
            return _fail("缺少备份文件名")
        result = self.store.restore_backup(name, self._actor())
        return _ok({"ok": result.ok, "message": result.message})

    # --------------------------------------------------------- import/export
    async def api_export(self) -> Response:
        args = request.args
        raw_keys = str(args.get("keys", "")).strip()
        keys = [item for item in (part.strip() for part in raw_keys.split("|")) if item] or None
        bundle = self.store.export_bundle(
            keys=keys,
            include_audit=_as_bool(args.get("include_audit"), False),
            audit_limit=_as_int(args.get("audit_limit"), 500, 1, 500),
            mask_user_ids=_as_bool(
                args.get("mask"), _as_bool(self.plugin.config.get("export_mask_user_ids", False))
            ),
        )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"profileweaver-{stamp}.json"
        body = json.dumps(bundle, ensure_ascii=False, indent=2)
        return Response(
            body,
            status=200,
            mimetype="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-ProfileWeaver-Count": str(bundle.get("profile_count", 0)),
            },
        )

    async def api_import(self) -> Response:
        if not self._allow_edit():
            return _fail("WebUI 当前为只读模式", 403)

        mode = "merge"
        payload: Any = None

        try:
            files = await request.files
        except Exception:  # pragma: no cover
            files = None
        if files:
            upload = files.get("file") or next(iter(files.values()), None)
            if upload is not None:
                raw = upload.read()
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                if len(raw) > MAX_UPLOAD_BYTES:
                    return _fail("文件过大（上限 16 MB）")
                try:
                    payload = json.loads(raw.decode("utf-8-sig"))
                except (UnicodeDecodeError, ValueError) as exc:
                    return _fail(f"文件不是合法的 UTF-8 JSON：{exc}")
            try:
                form = await request.form
                mode = str(form.get("mode", "") or request.args.get("mode", "") or "merge")
            except Exception:  # pragma: no cover
                mode = str(request.args.get("mode", "merge"))
        else:
            body = await self._body()
            mode = str(body.get("mode", "merge"))
            payload = body.get("payload")
            if payload is None and "profiles" in body:
                payload = body

        if payload is None:
            return _fail("没有收到导入内容")

        result = self.store.import_bundle(payload, mode=mode, actor=self._actor())
        response = jsonify(result)
        response.status_code = 200 if result.get("ok") else 400
        return response
