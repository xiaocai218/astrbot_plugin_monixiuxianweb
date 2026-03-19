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
            self._send_json(
                {
                    "ok": True,
                    "mode": self.service_meta.get("mode", "plugin"),
                    "host": self.service_meta.get("host"),
                    "port": self.service_meta.get("port"),
                }
            )
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
