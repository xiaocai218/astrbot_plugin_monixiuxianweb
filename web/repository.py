from __future__ import annotations

from pathlib import Path

from ..web_preview_server import WebPreviewRepository as LegacyWebPreviewRepository


class WebPreviewRepository(LegacyWebPreviewRepository):
    """Web 预览数据仓库入口。"""

    def __init__(self, db_path: Path):
        super().__init__(db_path)
