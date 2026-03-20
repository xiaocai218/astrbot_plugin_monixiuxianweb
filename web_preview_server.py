from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from .web.auth import WebAuthService
except ImportError:
    from web.auth import WebAuthService

try:
    from .web.common import WEB_DIR, detect_default_db, load_web_server_config
except ImportError:
    from web.common import WEB_DIR, detect_default_db, load_web_server_config

try:
    from .web.repository import WebPreviewRepositoryBase
except ImportError:
    from web.repository import WebPreviewRepositoryBase


class WebPreviewRepository(WebPreviewRepositoryBase):
    pass


# 低风险收口：优先复用共享仓库基类中的高频查询实现。
WebPreviewRepository.get_shop_preview = WebPreviewRepositoryBase.get_shop_preview
WebPreviewRepository.get_boss_preview = WebPreviewRepositoryBase.get_boss_preview
WebPreviewRepository.get_bank_preview = WebPreviewRepositoryBase.get_bank_preview
WebPreviewRepository.get_rift_preview = WebPreviewRepositoryBase.get_rift_preview
WebPreviewRepository.get_adventure_preview = WebPreviewRepositoryBase.get_adventure_preview
WebPreviewRepository.get_bounty_preview = WebPreviewRepositoryBase.get_bounty_preview
WebPreviewRepository.get_spirit_eye_preview = WebPreviewRepositoryBase.get_spirit_eye_preview
WebPreviewRepository.get_sect_preview = WebPreviewRepositoryBase.get_sect_preview
WebPreviewRepository.get_blessed_land_preview = WebPreviewRepositoryBase.get_blessed_land_preview
WebPreviewRepository.get_spirit_farm_preview = WebPreviewRepositoryBase.get_spirit_farm_preview
WebPreviewRepository.get_inventory_preview = WebPreviewRepositoryBase.get_inventory_preview
WebPreviewRepository.get_dual_cultivation_preview = WebPreviewRepositoryBase.get_dual_cultivation_preview


class WebPreviewHandler(SimpleHTTPRequestHandler):
    repo: WebPreviewRepository | None = None
    db_path: Path | None = None
    auth_service: WebAuthService | None = None

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

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
            defaults = load_web_server_config()
            auth_status = (self.auth_service or WebAuthService.from_config(self.db_path)).get_status()
            self._send_json(
                {
                    "ok": True,
                    "mode": "standalone",
                    "host": defaults["host"],
                    "port": defaults["port"],
                    "auth_enabled": defaults.get("auth_enabled", False),
                    "guest_access": defaults.get("guest_access", True),
                    "storage_ready": auth_status.get("storage_ready", False),
                }
            )
            return

        if parsed.path == "/api/auth/status":
            auth_service = self.auth_service or WebAuthService.from_config(self.db_path)
            self._send_json(auth_service.get_status())
            return

        if parsed.path == "/api/auth/bind-code":
            params = parse_qs(parsed.query)
            bind_code = (params.get("code") or [""])[0].strip()
            if not bind_code:
                self._send_json({"ok": False, "error": "缺少绑定码"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service or WebAuthService.from_config(self.db_path)
            payload = auth_service.inspect_bind_code(bind_code)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/auth/login":
            params = parse_qs(parsed.query)
            bind_code = (params.get("code") or [""])[0].strip()
            if not bind_code:
                self._send_json({"ok": False, "error": "缺少绑定码"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service or WebAuthService.from_config(self.db_path)
            payload = auth_service.exchange_bind_code(bind_code)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/auth/session":
            params = parse_qs(parsed.query)
            token = (params.get("token") or [""])[0].strip()
            if not token:
                self._send_json({"ok": False, "error": "缺少 token"}, status=HTTPStatus.BAD_REQUEST)
                return
            auth_service = self.auth_service or WebAuthService.from_config(self.db_path)
            payload = auth_service.get_session(token)
            self._send_json(payload, status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/players":
            self._send_json(
                {
                    "ok": True,
                    "players": self.repo.get_players(),
                    "world": self.repo.get_world_summary(),
                }
            )
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


def parse_args() -> argparse.Namespace:
    defaults = load_web_server_config()
    parser = argparse.ArgumentParser(description="修仙 Web 预览服务")
    parser.add_argument(
        "--host",
        default=None,
        help="监听地址，默认读取 config/game_config.json 中的 web_server.host，缺省为 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        default=None,
        type=int,
        help="监听端口，默认读取 config/game_config.json 中的 web_server.port，缺省为 8765",
    )
    parser.add_argument("--db", type=Path, default=detect_default_db(), help="数据库文件路径")
    args = parser.parse_args()
    if not args.host:
        args.host = defaults["host"]
    if args.port is None:
        args.port = defaults["port"]
    return args


def main():
    args = parse_args()
    db_path = args.db
    if not db_path or not db_path.exists():
        raise SystemExit(
            "未找到数据库文件，请使用 --db 指定路径，例如：\n"
            "python web_preview_server.py --db F:\\Download\\xiuxian_data_lite.db"
        )

    WebPreviewHandler.repo = WebPreviewRepository(db_path)
    WebPreviewHandler.db_path = db_path
    WebPreviewHandler.auth_service = WebAuthService.from_config(db_path)

    server = ThreadingHTTPServer((args.host, args.port), WebPreviewHandler)
    print(f"修仙 Web 预览已启动：http://{args.host}:{args.port}")
    print(f"当前数据库：{db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
