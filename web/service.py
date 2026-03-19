from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from astrbot.api import logger

from ..web_preview_server import WEB_DIR, load_web_server_config
from .http_handler import PluginWebPreviewHandler
from .repository import WebPreviewRepository


class WebPreviewService:
    """插件内置的只读 Web 预览服务。"""

    def __init__(self, db_path: Path, host: str, port: int):
        self.db_path = Path(db_path)
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @classmethod
    def from_config(cls, db_path: Path) -> tuple["WebPreviewService", bool]:
        config = load_web_server_config()
        service = cls(
            db_path=Path(db_path),
            host=str(config["host"]),
            port=int(config["port"]),
        )
        return service, bool(config.get("enabled", False))

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return

        handler_cls = type("RuntimePluginWebPreviewHandler", (PluginWebPreviewHandler,), {})
        handler_cls.repo = WebPreviewRepository(self.db_path)
        handler_cls.db_path = self.db_path
        handler_cls.service_meta = {
            "mode": "plugin",
            "host": self.host,
            "port": self.port,
        }

        self._server = ThreadingHTTPServer(
            (self.host, self.port),
            partial(handler_cls, directory=WEB_DIR),
        )
        self._thread = Thread(
            target=self._server.serve_forever,
            name="xiuxian-web-preview",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"【修仙插件】只读 Web 预览已启动：{self.url}")

    def stop(self) -> None:
        if not self._server:
            return

        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            self._server = None
            self._thread = None
            logger.info("【修仙插件】只读 Web 预览已关闭。")
