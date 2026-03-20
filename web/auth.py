from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import load_web_server_config


WEB_AUTH_TABLES = (
    "web_bind_keys",
    "web_tokens",
    "web_chat_bindings",
)


@dataclass(slots=True)
class WebAuthState:
    enabled: bool
    guest_access: bool
    storage_ready: bool
    missing_tables: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "guest_access": self.guest_access,
            "mode": "reserved" if self.enabled else "disabled",
            "login_required": False,
            "binding_required": False,
            "writable_api_enabled": False,
            "storage_ready": self.storage_ready,
            "required_tables": list(WEB_AUTH_TABLES),
            "missing_tables": self.missing_tables,
            "message": self._message(),
        }

    def _message(self) -> str:
        if not self.enabled:
            return "当前为游客只读模式，尚未启用 Web 鉴权。"
        if not self.storage_ready:
            return "Web 轻量鉴权预留层已启用，但绑定存储表尚未完全就绪。"
        return "Web 轻量鉴权预留层已启用，当前仍保持只读模式。"


class WebAuthService:
    """Web 轻量鉴权与绑定预留服务。"""

    TOKEN_EXPIRE_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, db_path: Path | None, enabled: bool, guest_access: bool):
        self.db_path = Path(db_path) if db_path else None
        self.enabled = enabled
        self.guest_access = guest_access

    @classmethod
    def from_config(cls, db_path: Path | None = None) -> "WebAuthService":
        config = load_web_server_config()
        return cls(
            db_path=db_path,
            enabled=bool(config.get("auth_enabled", False)),
            guest_access=bool(config.get("guest_access", True)),
        )

    def get_status(self) -> dict[str, Any]:
        missing_tables = self._missing_tables()
        return WebAuthState(
            enabled=self.enabled,
            guest_access=self.guest_access,
            storage_ready=not missing_tables,
            missing_tables=missing_tables,
        ).to_payload()

    def inspect_bind_code(self, bind_code: str) -> dict[str, Any]:
        code = (bind_code or "").strip().upper()
        if not code:
            return {"ok": False, "error": "缺少绑定码"}

        if not self.db_path or not self.db_path.exists():
            return {"ok": False, "error": "绑定存储未就绪"}

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT id, bind_code, user_id, platform, status, created_at, expire_at, used_at
                    FROM web_bind_keys
                    WHERE bind_code = ?
                    LIMIT 1
                    """,
                    (code,),
                ).fetchone()

                if not row:
                    return {
                        "ok": True,
                        "exists": False,
                        "valid": False,
                        "status": "missing",
                        "bind_code": code,
                        "message": "未找到该绑定码，请确认输入是否正确。",
                    }

                status = str(row["status"] or "pending")
                now = int(time.time())
                expire_at = int(row["expire_at"] or 0)
                used_at = int(row["used_at"] or 0)

                if status == "pending" and expire_at and expire_at < now:
                    conn.execute("UPDATE web_bind_keys SET status = 'expired' WHERE id = ?", (row["id"],))
                    conn.commit()
                    status = "expired"

                remaining_seconds = max(0, expire_at - now) if expire_at else 0
                payload = {
                    "ok": True,
                    "exists": True,
                    "valid": status == "pending",
                    "status": status,
                    "bind_code": row["bind_code"],
                    "platform": row["platform"],
                    "remaining_seconds": remaining_seconds,
                    "remaining_minutes": remaining_seconds // 60,
                    "used": status == "used",
                    "message": self._bind_code_message(status, remaining_seconds),
                }
                if used_at:
                    payload["used_at"] = used_at
                return payload
            finally:
                conn.close()
        except Exception:
            return {"ok": False, "error": "绑定码校验失败"}

    def exchange_bind_code(self, bind_code: str) -> dict[str, Any]:
        code = (bind_code or "").strip().upper()
        if not code:
            return {"ok": False, "error": "缺少绑定码"}

        if not self.db_path or not self.db_path.exists():
            return {"ok": False, "error": "绑定存储未就绪"}

        now = int(time.time())
        expire_at = now + self.TOKEN_EXPIRE_SECONDS
        token = secrets.token_urlsafe(32)

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT id, bind_code, user_id, platform, status, expire_at
                    FROM web_bind_keys
                    WHERE bind_code = ?
                    LIMIT 1
                    """,
                    (code,),
                ).fetchone()
                if not row:
                    return {"ok": False, "error": "未找到该绑定码"}

                status = str(row["status"] or "pending")
                bind_expire_at = int(row["expire_at"] or 0)
                if status == "pending" and bind_expire_at and bind_expire_at < now:
                    conn.execute("UPDATE web_bind_keys SET status = 'expired' WHERE id = ?", (row["id"],))
                    conn.commit()
                    status = "expired"

                if status != "used":
                    if status == "pending":
                        return {"ok": False, "error": "该绑定码尚未在聊天端完成绑定，请先发送“绑定网页 <绑定码>”。"}
                    if status == "expired":
                        return {"ok": False, "error": "该绑定码已过期，请重新生成。"}
                    return {"ok": False, "error": "该绑定码当前不可用于登录。"}

                binding = conn.execute(
                    """
                    SELECT user_id, platform, chat_user_id, chat_user_name
                    FROM web_chat_bindings
                    WHERE user_id = ? AND platform = ?
                    LIMIT 1
                    """,
                    (row["user_id"], row["platform"]),
                ).fetchone()
                if not binding:
                    return {"ok": False, "error": "绑定关系不存在，请重新生成绑定码。"}

                conn.execute(
                    "UPDATE web_tokens SET revoked = 1 WHERE user_id = ? AND platform = ? AND revoked = 0",
                    (binding["user_id"], binding["platform"]),
                )
                conn.execute(
                    """
                    INSERT INTO web_tokens (
                        token, user_id, platform, created_at, expire_at, revoked
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (token, binding["user_id"], binding["platform"], now, expire_at),
                )
                conn.commit()
                return {
                    "ok": True,
                    "token": token,
                    "expire_at": expire_at,
                    "expires_in_seconds": self.TOKEN_EXPIRE_SECONDS,
                    "user_id": binding["user_id"],
                    "platform": binding["platform"],
                    "chat_user_name": binding["chat_user_name"],
                    "message": "已建立 Web 只读登录会话，当前仍为只读模式。",
                }
            finally:
                conn.close()
        except Exception:
            return {"ok": False, "error": "建立 Web 登录会话失败"}

    def get_session(self, token: str) -> dict[str, Any]:
        value = (token or "").strip()
        if not value:
            return {"ok": False, "error": "缺少 token"}

        if not self.db_path or not self.db_path.exists():
            return {"ok": False, "error": "会话存储未就绪"}

        now = int(time.time())
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT token, user_id, platform, created_at, expire_at, revoked
                    FROM web_tokens
                    WHERE token = ?
                    LIMIT 1
                    """,
                    (value,),
                ).fetchone()
                if not row:
                    return {"ok": True, "authenticated": False, "message": "当前没有有效的 Web 登录会话。"}

                if int(row["revoked"] or 0) == 1:
                    return {"ok": True, "authenticated": False, "message": "当前登录会话已失效，请重新换取新会话。"}

                expire_at = int(row["expire_at"] or 0)
                if expire_at and expire_at < now:
                    conn.execute("UPDATE web_tokens SET revoked = 1 WHERE token = ?", (value,))
                    conn.commit()
                    return {"ok": True, "authenticated": False, "message": "当前登录会话已过期，请重新换取新会话。"}

                remaining_seconds = max(0, expire_at - now) if expire_at else 0
                return {
                    "ok": True,
                    "authenticated": True,
                    "user_id": row["user_id"],
                    "platform": row["platform"],
                    "remaining_seconds": remaining_seconds,
                    "remaining_minutes": remaining_seconds // 60,
                    "message": "当前 Web 会话有效，已进入只读登录态。",
                }
            finally:
                conn.close()
        except Exception:
            return {"ok": False, "error": "读取 Web 登录会话失败"}

    def _missing_tables(self) -> list[str]:
        if not self.db_path or not self.db_path.exists():
            return list(WEB_AUTH_TABLES)

        try:
            conn = sqlite3.connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?)",
                    WEB_AUTH_TABLES,
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return list(WEB_AUTH_TABLES)

        existing = {str(row[0]) for row in rows}
        return [table_name for table_name in WEB_AUTH_TABLES if table_name not in existing]

    @staticmethod
    def _bind_code_message(status: str, remaining_seconds: int) -> str:
        if status == "pending":
            return f"绑定码有效，剩余约 {remaining_seconds // 60} 分 {remaining_seconds % 60} 秒。"
        if status == "used":
            return "该绑定码已被使用，可重新在聊天端生成新的绑定码。"
        if status == "expired":
            return "该绑定码已过期，请重新在聊天端生成。"
        return "该绑定码当前不可用。"
