"""个人信息图片卡片生成器。"""

import asyncio
import logging
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

__all__ = ["ImageGenerator"]


class ImageGenerator:
    """生成适合聊天场景阅读的个人信息卡片。"""

    CARD_WIDTH = 1600
    MIN_CARD_HEIGHT = 1320
    PAGE_PADDING = 56
    COLUMN_GAP = 48
    SECTION_GAP = 28

    BACKGROUND_COLOR = (9, 15, 28)
    OVERLAY_COLOR = (5, 10, 18, 108)
    PANEL_COLOR = (12, 20, 36, 196)
    PANEL_BORDER_COLOR = (211, 178, 92, 208)
    TITLE_COLOR = "#F5D08A"
    LABEL_COLOR = "#DCE5F8"
    VALUE_COLOR = "#F8FBFF"
    SUBTITLE_COLOR = "#C5D0E7"
    SHADOW_COLOR = (0, 0, 0, 150)

    PANEL_RADIUS = 34
    PANEL_BORDER_WIDTH = 3
    PANEL_PADDING_X = 34
    PANEL_PADDING_TOP = 102
    PANEL_PADDING_BOTTOM = 34
    PANEL_TITLE_OFFSET_Y = 24

    def __init__(self):
        self.has_pil = HAS_PIL
        self.assets_dir = Path(__file__).resolve().parent.parent / "resources" / "profile_card"
        self.output_dir = Path(tempfile.gettempdir()) / "astrbot_monixiuxian2_cards"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.has_pil:
            logger.warning("【模拟修仙】未检测到 Pillow，个人信息图片卡片不可用。")

    async def generate_user_info_card(self, user_id: str, detail_map: Dict) -> Optional[str]:
        """生成个人信息图片并返回本地路径。"""
        if not self.has_pil:
            return None

        try:
            return await asyncio.to_thread(self._render_card, user_id, detail_map)
        except Exception as exc:
            logger.error(f"【模拟修仙】生成个人信息卡片失败：{exc}")
            return None

    def _render_card(self, user_id: str, detail_map: Dict) -> str:
        title_font = self._get_font(124, bold=True, strict=True)
        subtitle_font = self._get_font(32, strict=True)
        section_font = self._get_font(50, bold=True, strict=True)
        label_font = self._get_font(28, bold=True, strict=True)
        value_font = self._get_font(38, strict=True)
        tip_label_font = self._get_font(28, bold=True, strict=True)
        tip_font = self._get_font(36, strict=True)

        sections = self._build_section_layout(detail_map)
        width, height = self._resolve_card_size(sections, value_font, tip_font)

        image = self._build_background(width, height)
        draw = ImageDraw.Draw(image)

        current_y = self.PAGE_PADDING
        self._draw_glow_title(draw, (self.PAGE_PADDING, current_y), "道友信息", title_font, self.TITLE_COLOR)
        current_y += 136

        subtitle = f"ID: {user_id}    生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        draw.text((self.PAGE_PADDING + 6, current_y), subtitle, font=subtitle_font, fill=self.SUBTITLE_COLOR)
        current_y += 72

        left_width = (width - self.PAGE_PADDING * 2 - self.COLUMN_GAP) // 2
        right_width = left_width
        left_x = self.PAGE_PADDING
        right_x = self.PAGE_PADDING + left_width + self.COLUMN_GAP
        left_y = current_y
        right_y = current_y

        for section in sections:
            if section["column"] == "full":
                target_x = self.PAGE_PADDING
                target_y = max(left_y, right_y)
                target_width = width - self.PAGE_PADDING * 2
            else:
                target_x = left_x if section["column"] == "left" else right_x
                target_y = left_y if section["column"] == "left" else right_y
                target_width = left_width if section["column"] == "left" else right_width
            content_font = value_font if section["kind"] != "tips" else tip_font
            section_height = self._estimate_section_height(
                target_width,
                section["rows"],
                content_font,
                columns=section["columns"],
                line_gap=52 if section["kind"] != "tips" else 48,
            )

            self._draw_section(
                image=image,
                title=section["title"],
                rows=section["rows"],
                rect=(target_x, target_y, target_width, section_height),
                section_font=section_font,
                label_font=label_font if section["kind"] != "tips" else tip_label_font,
                value_font=content_font,
                columns=section["columns"],
            )

            if section["column"] == "left":
                left_y += section_height + self.SECTION_GAP
            elif section["column"] == "right":
                right_y += section_height + self.SECTION_GAP
            else:
                next_y = target_y + section_height + self.SECTION_GAP
                left_y = next_y
                right_y = next_y

        output_path = self.output_dir / f"user_info_{self._safe_name(user_id)}.jpg"
        rgb_image = image.convert("RGB")
        rgb_image.save(output_path, format="JPEG", quality=90, optimize=True, progressive=True)
        return str(output_path)

    def _build_section_layout(self, detail_map: Dict) -> List[Dict]:
        basic_rows = detail_map.get("basic_info", [])
        cultivation_rows = detail_map.get("cultivation_info", [])
        equipment_rows = detail_map.get("equipment_info", [])
        other_rows = detail_map.get("other_info", [])
        tips = [tip for tip in detail_map.get("tips", []) if tip]
        tip_rows = [(f"提示 {index + 1}", tip) for index, tip in enumerate(tips)]

        layout: List[Dict] = []

        if basic_rows or cultivation_rows:
            layout.extend(
                [
                    {
                        "title": "基本信息",
                        "rows": basic_rows,
                        "columns": 2,
                        "kind": "normal",
                        "column": "left",
                    },
                    {
                        "title": "修炼属性",
                        "rows": cultivation_rows,
                        "columns": 2,
                        "kind": "normal",
                        "column": "right",
                    },
                ]
            )

        if equipment_rows or other_rows:
            layout.extend(
                [
                    {
                        "title": "装备与灵宠",
                        "rows": equipment_rows,
                        "columns": 1,
                        "kind": "normal",
                        "column": "left",
                    },
                    {
                        "title": "宗门与其他",
                        "rows": other_rows,
                        "columns": 1,
                        "kind": "normal",
                        "column": "right",
                    },
                ]
            )

        if tip_rows:
            layout.append(
                {
                    "title": "状态提示",
                    "rows": tip_rows,
                    "columns": 1,
                    "kind": "tips",
                    "column": "full",
                }
            )

        return layout

    def _resolve_card_size(self, layout: Sequence[Dict], value_font, tip_font) -> Tuple[int, int]:
        width = self.CARD_WIDTH
        current_height = self.PAGE_PADDING + 260
        column_width = (width - self.PAGE_PADDING * 2 - self.COLUMN_GAP) // 2
        left_height = current_height
        right_height = current_height
        full_width = width - self.PAGE_PADDING * 2

        for section in layout:
            font = value_font if section["kind"] != "tips" else tip_font
            target_width = full_width if section["column"] == "full" else column_width
            section_height = self._estimate_section_height(
                target_width,
                section["rows"],
                font,
                columns=section["columns"],
                line_gap=52 if section["kind"] != "tips" else 48,
            )
            if section["column"] == "left":
                left_height += section_height + self.SECTION_GAP
            elif section["column"] == "right":
                right_height += section_height + self.SECTION_GAP
            else:
                max_height = max(left_height, right_height)
                left_height = max_height + section_height + self.SECTION_GAP
                right_height = left_height

        return width, max(self.MIN_CARD_HEIGHT, max(left_height, right_height) + self.PAGE_PADDING)

    def _build_background(self, width: int, height: int) -> Image.Image:
        background = self._load_background_image(width, height)
        if background is None:
            background = Image.new("RGB", (width, height), self.BACKGROUND_COLOR)
            self._paint_fallback_background(background)

        overlay = Image.new("RGBA", (width, height), self.OVERLAY_COLOR)
        return Image.alpha_composite(background.convert("RGBA"), overlay)

    def _load_background_image(self, width: int, height: int) -> Optional[Image.Image]:
        candidates = [
            path
            for path in sorted(self.assets_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        if not candidates:
            return None

        selected = random.choice(candidates)
        logger.info(f"【模拟修仙】使用背景素材：{selected.name}")
        with Image.open(selected) as source:
            image = source.convert("RGBA")
            ratio = max(width / image.width, height / image.height)
            resized = image.resize((int(image.width * ratio), int(image.height * ratio)))
            left = max(0, (resized.width - width) // 2)
            top = max(0, (resized.height - height) // 2)
            return resized.crop((left, top, left + width, top + height))

    def _paint_fallback_background(self, image: Image.Image):
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, image.width, image.height), fill=self.BACKGROUND_COLOR)
        draw.ellipse((1020, -120, 1750, 480), fill=ImageColor.getrgb("#1B3559"))
        draw.ellipse((-220, 980, 560, 1860), fill=ImageColor.getrgb("#2B2149"))
        draw.ellipse((260, 220, 760, 780), fill=ImageColor.getrgb("#17363B"))

    def _draw_section(
        self,
        image: Image.Image,
        title: str,
        rows: Sequence[Tuple[str, str]],
        rect: Tuple[int, int, int, int],
        section_font,
        label_font,
        value_font,
        columns: int = 1,
    ):
        x, y, width, height = rect

        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=self.PANEL_RADIUS,
            fill=self.PANEL_COLOR,
            outline=self.PANEL_BORDER_COLOR,
            width=self.PANEL_BORDER_WIDTH,
        )

        shadow = Image.new("RGBA", (width + 44, height + 44), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (18, 18, width + 18, height + 18),
            radius=self.PANEL_RADIUS + 6,
            fill=self.SHADOW_COLOR,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        image.alpha_composite(shadow, (x - 22, y - 22))
        image.alpha_composite(panel, (x, y))

        draw = ImageDraw.Draw(image)
        self._draw_glow_title(draw, (x + 30, y + self.PANEL_TITLE_OFFSET_Y), title, section_font, self.TITLE_COLOR)

        content_left = x + self.PANEL_PADDING_X
        content_top = y + self.PANEL_PADDING_TOP
        content_width = width - self.PANEL_PADDING_X * 2
        column_count = 1 if columns <= 1 else 2
        column_gap = self.COLUMN_GAP
        column_width = content_width if column_count == 1 else (content_width - column_gap) // 2

        if column_count == 2:
            self._draw_split_columns(
                draw=draw,
                rows=rows,
                content_left=content_left,
                content_top=content_top,
                column_width=column_width,
                column_gap=column_gap,
                label_font=label_font,
                value_font=value_font,
            )
            return

        current_y = content_top
        label_width = 156
        value_width = max(220, column_width - label_width - 18)
        for label, value in rows:
            wrapped_lines = self._wrap_text(draw, str(value), value_font, value_width)
            draw.text((content_left, current_y), str(label), font=label_font, fill=self.LABEL_COLOR)
            value_x = content_left + label_width
            for line_index, line in enumerate(wrapped_lines):
                draw.text((value_x, current_y + line_index * 40), line, font=value_font, fill=self.VALUE_COLOR)
            block_height = max(64, len(wrapped_lines) * 40 + 10)
            current_y += block_height

    def _estimate_section_height(
        self,
        width: int,
        rows: Sequence[Tuple[str, str]],
        value_font,
        columns: int = 1,
        line_gap: int = 64,
    ) -> int:
        if not rows:
            return 170

        scratch = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)

        content_width = width - self.PANEL_PADDING_X * 2
        column_count = 1 if columns <= 1 else 2
        column_gap = self.COLUMN_GAP
        column_width = content_width if column_count == 1 else (content_width - column_gap) // 2

        if column_count == 2:
            split_index = (len(rows) + 1) // 2
            left_rows = rows[:split_index]
            right_rows = rows[split_index:]
            return self.PANEL_PADDING_TOP + max(
                self._estimate_column_height(draw, left_rows, column_width, label_font=None, value_font=value_font),
                self._estimate_column_height(draw, right_rows, column_width, label_font=None, value_font=value_font),
            ) + self.PANEL_PADDING_BOTTOM

        label_width = 156
        value_width = max(220, column_width - label_width - 18)
        total = 0
        for _label, value in rows:
            wrapped_lines = self._wrap_text(draw, str(value), value_font, value_width)
            total += max(line_gap, len(wrapped_lines) * 40 + 10)
        return self.PANEL_PADDING_TOP + total + self.PANEL_PADDING_BOTTOM

    def _estimate_column_height(
        self,
        draw: ImageDraw.ImageDraw,
        rows: Sequence[Tuple[str, str]],
        column_width: int,
        label_font,
        value_font,
    ) -> int:
        if not rows:
            return 0

        total = 0
        value_width = max(200, column_width - 24)
        for _label, value in rows:
            wrapped_lines = self._wrap_text(draw, str(value), value_font, value_width)
            total += max(110, 42 + len(wrapped_lines) * 42)
        return total

    def _draw_split_columns(
        self,
        draw: ImageDraw.ImageDraw,
        rows: Sequence[Tuple[str, str]],
        content_left: int,
        content_top: int,
        column_width: int,
        column_gap: int,
        label_font,
        value_font,
    ):
        split_index = (len(rows) + 1) // 2
        left_rows = rows[:split_index]
        right_rows = rows[split_index:]

        self._draw_column_rows(
            draw=draw,
            rows=left_rows,
            x=content_left,
            y=content_top,
            column_width=column_width,
            label_font=label_font,
            value_font=value_font,
        )
        self._draw_column_rows(
            draw=draw,
            rows=right_rows,
            x=content_left + column_width + column_gap,
            y=content_top,
            column_width=column_width,
            label_font=label_font,
            value_font=value_font,
        )

    def _draw_column_rows(
        self,
        draw: ImageDraw.ImageDraw,
        rows: Sequence[Tuple[str, str]],
        x: int,
        y: int,
        column_width: int,
        label_font,
        value_font,
    ):
        current_y = y
        value_width = max(200, column_width - 24)
        for label, value in rows:
            wrapped_lines = self._wrap_text(draw, str(value), value_font, value_width)
            draw.text((x, current_y), str(label), font=label_font, fill=self.LABEL_COLOR)
            value_y = current_y + 38
            for line_index, line in enumerate(wrapped_lines):
                draw.text((x, value_y + line_index * 42), line, font=value_font, fill=self.VALUE_COLOR)
            current_y += max(110, 42 + len(wrapped_lines) * 42)

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
        if not text:
            return [""]

        lines: List[str] = []
        current = ""
        for char in text:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if current and (bbox[2] - bbox[0]) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate

        if current:
            lines.append(current)

        return lines[:3]

    def _draw_glow_title(self, draw: ImageDraw.ImageDraw, position: Tuple[int, int], text: str, font, fill: str):
        x, y = position
        glow_color = ImageColor.getrgb("#76561B")
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
        draw.text((x, y), text, font=font, fill=fill)

    def _get_font(self, size: int, bold: bool = False, strict: bool = False):
        for path in self._candidate_fonts(bold):
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue

        if strict:
            raise RuntimeError("未找到可用的中文字体，可将字体文件放入 resources/profile_card/fonts/ 后重试。")
        return ImageFont.load_default()

    def _candidate_fonts(self, bold: bool) -> Iterable[Path]:
        local_fonts = [
            self.assets_dir / "fonts" / "font.ttf",
            self.assets_dir / "fonts" / "font.ttc",
            self.assets_dir / "fonts" / "font.otf",
            self.assets_dir / "font.ttf",
            self.assets_dir / "font.ttc",
            self.assets_dir / "font.otf",
        ]
        for path in local_fonts:
            yield path

        fonts_dir = self.assets_dir / "fonts"
        if fonts_dir.exists():
            preferred_names = [
                "NotoSansCJKsc-Bold.otf" if bold else "NotoSansCJKsc-Regular.otf",
                "NotoSansSC-Bold.ttf" if bold else "NotoSansSC-Regular.ttf",
                "SourceHanSansSC-Bold.otf" if bold else "SourceHanSansSC-Regular.otf",
                "SourceHanSansCN-Bold.otf" if bold else "SourceHanSansCN-Regular.otf",
                "msyhbd.ttc" if bold else "msyh.ttc",
                "simhei.ttf" if bold else "simsun.ttc",
                "wqy-zenhei.ttc",
                "wqy-microhei.ttc",
            ]
            for name in preferred_names:
                yield fonts_dir / name
            for pattern in ("*.ttf", "*.ttc", "*.otf"):
                for path in sorted(fonts_dir.glob(pattern)):
                    yield path

        linux_candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansSC-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
            Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
        ]
        for path in linux_candidates:
            yield path

        windows_dir = Path("C:/Windows/Fonts")
        font_names = [
            "msyhbd.ttc" if bold else "msyh.ttc",
            "simhei.ttf" if bold else "simsun.ttc",
            "SourceHanSansSC-Bold.otf" if bold else "SourceHanSansSC-Regular.otf",
            "arialbd.ttf" if bold else "arial.ttf",
        ]
        for name in font_names:
            yield windows_dir / name

    def _safe_name(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
