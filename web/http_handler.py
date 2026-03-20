from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


class PluginWebPreviewHandler(SimpleHTTPRequestHandler):
    """插件内置模式使用的只读 Web 处理器。"""

    repo = None
    db_path: Path | None = None
    service_meta: dict[str, Any] = {}
    auth_service = None

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(directory), **kwargs)

    def log_message(self, format, *args):
        print("[web-preview]", format % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_api(self, parsed):
        if not self.repo or not self.db_path:
            self._send_json({"ok": False, "error": "数据库未配置"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/health":
            self._send_json({"ok": True, "db_path": str(self.db_path)})
            return

        if parsed.path == "/api/status":
            auth_status = self.auth_service.get_status() if self.auth_service else {}
            self._send_json(
                {
                    "ok": True,
                    "mode": self.service_meta.get("mode", "plugin"),
                    "host": self.service_meta.get("host"),
                    "port": self.service_meta.get("port"),
                    "auth_enabled": auth_status.get("enabled", False),
                    "guest_access": auth_status.get("guest_access", True),
                    "storage_ready": auth_status.get("storage_ready", False),
                }
            )
            return

        if parsed.path == "/api/auth/status":
            if self.auth_service:
                self._send_json(self.auth_service.get_status())
            else:
                self._send_json(
                    {
                        "ok": True,
                        "enabled": False,
                        "guest_access": True,
                        "mode": "disabled",
                        "login_required": False,
                        "binding_required": False,
                        "writable_api_enabled": False,
                        "storage_ready": False,
                        "required_tables": [],
                        "missing_tables": [],
                        "message": "当前未挂载 Web 鉴权服务，保持游客只读模式。",
                    }
                )
            return

        if parsed.path == "/api/auth/bind-code":
            params = parse_qs(parsed.query)
            bind_code = (params.get("code") or [""])[0].strip()
            if not bind_code:
                self._send_json({"ok": False, "error": "缺少绑定码"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service
            if not auth_service:
                self._send_json({"ok": False, "error": "Web 鉴权服务未挂载"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            payload = auth_service.inspect_bind_code(bind_code)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/auth/login":
            params = parse_qs(parsed.query)
            bind_code = (params.get("code") or [""])[0].strip()
            if not bind_code:
                self._send_json({"ok": False, "error": "缺少绑定码"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service
            if not auth_service:
                self._send_json({"ok": False, "error": "Web 鉴权服务未挂载"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            payload = auth_service.exchange_bind_code(bind_code)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/auth/session":
            params = parse_qs(parsed.query)
            token = (params.get("token") or [""])[0].strip()
            if not token:
                self._send_json({"ok": False, "error": "缺少 token"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service
            if not auth_service:
                self._send_json({"ok": False, "error": "Web 鉴权服务未挂载"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            payload = auth_service.get_session(token)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/players":
            self._send_json({"ok": True, "players": self.repo.get_players(), "world": self.repo.get_world_summary()})
            return

        if parsed.path == "/api/dashboard":
            params = parse_qs(parsed.query)
            user_id = (params.get("user_id") or [""])[0].strip()
            if not user_id:
                self._send_json({"ok": False, "error": "缺少 user_id"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                dashboard = self.repo.get_dashboard(user_id)
            except KeyError:
                self._send_json({"ok": False, "error": f"未找到玩家：{user_id}"}, status=HTTPStatus.NOT_FOUND)
                return

            self._send_json({"ok": True, **dashboard})
            return

        self._send_json({"ok": False, "error": "未知接口"}, status=HTTPStatus.NOT_FOUND)
