"""修仙个人信息图片卡片生成器。"""

import asyncio
import logging
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

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
    """生成更适合聊天场景阅读的个人信息卡片。"""

    CARD_SIZE = (1440, 1880)
    PAGE_PADDING = 64
    BACKGROUND_COLOR = (9, 15, 28)
    OVERLAY_COLOR = (4, 10, 18, 118)
    PANEL_COLOR = (15, 22, 38, 230)
    PANEL_BORDER_COLOR = (206, 176, 92, 215)
    TITLE_COLOR = "#F5D08A"
    LABEL_COLOR = "#D7E1F7"
    VALUE_COLOR = "#F7FAFF"
    SUBTITLE_COLOR = "#A9B6D4"
    SHADOW_COLOR = (0, 0, 0, 148)

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
        width, height = self.CARD_SIZE
        image = self._build_background(width, height)
        draw = ImageDraw.Draw(image)

        title_font = self._get_font(86, bold=True)
        subtitle_font = self._get_font(28)
        section_font = self._get_font(42, bold=True)
        label_font = self._get_font(34, bold=True)
        value_font = self._get_font(36)
        tip_font = self._get_font(30)

        current_y = self.PAGE_PADDING

        self._draw_glow_title(draw, (self.PAGE_PADDING, current_y), "道友信息", title_font, self.TITLE_COLOR)
        current_y += 102

        subtitle = f"ID: {user_id}    生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        draw.text((self.PAGE_PADDING + 4, current_y), subtitle, font=subtitle_font, fill=self.SUBTITLE_COLOR)
        current_y += 64

        sections = [
            ("基本信息", detail_map.get("basic_info", [])),
            ("修炼属性", detail_map.get("cultivation_info", [])),
            ("装备与灵宠", detail_map.get("equipment_info", [])),
            ("宗门与其他", detail_map.get("other_info", [])),
        ]

        for title, rows in sections:
            if not rows:
                continue
            panel_height = self._estimate_section_height(rows, value_font)
            self._draw_section(
                image=image,
                title=title,
                rows=rows,
                rect=(self.PAGE_PADDING, current_y, width - self.PAGE_PADDING * 2, panel_height),
                section_font=section_font,
                label_font=label_font,
                value_font=value_font,
            )
            current_y += panel_height + 30

        tips = [tip for tip in detail_map.get("tips", []) if tip]
        if tips:
            tip_rows = [("提示", tip) for tip in tips]
            tip_height = self._estimate_section_height(tip_rows, tip_font, line_height=50)
            self._draw_section(
                image=image,
                title="状态提示",
                rows=tip_rows,
                rect=(self.PAGE_PADDING, current_y, width - self.PAGE_PADDING * 2, tip_height),
                section_font=section_font,
                label_font=label_font,
                value_font=tip_font,
                line_height=50,
            )

        output_path = self.output_dir / f"user_info_{self._safe_name(user_id)}.png"
        image.save(output_path, format="PNG")
        return str(output_path)

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
        draw.ellipse((840, -120, 1500, 380), fill=ImageColor.getrgb("#1B3559"))
        draw.ellipse((-180, 1180, 420, 1900), fill=ImageColor.getrgb("#2B2149"))
        draw.ellipse((220, 280, 560, 680), fill=ImageColor.getrgb("#17363B"))

    def _draw_section(
        self,
        image: Image.Image,
        title: str,
        rows: Iterable[tuple[str, str]],
        rect: tuple[int, int, int, int],
        section_font,
        label_font,
        value_font,
        line_height: int = 56,
    ):
        x, y, width, height = rect

        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=34,
            fill=self.PANEL_COLOR,
            outline=self.PANEL_BORDER_COLOR,
            width=3,
        )

        shadow = Image.new("RGBA", (width + 44, height + 44), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (18, 18, width + 18, height + 18),
            radius=40,
            fill=self.SHADOW_COLOR,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        image.alpha_composite(shadow, (x - 22, y - 22))
        image.alpha_composite(panel, (x, y))

        draw = ImageDraw.Draw(image)
        self._draw_glow_title(draw, (x + 32, y + 24), title, section_font, self.TITLE_COLOR)

        start_y = y + 96
        label_x = x + 34
        value_x = x + 290
        value_width = width - 330

        line_spacing = 40
        current_y = start_y
        for label, value in rows:
            wrapped_lines = self._wrap_text(draw, str(value), value_font, value_width)
            draw.text((label_x, current_y), str(label), font=label_font, fill=self.LABEL_COLOR)
            for line_index, line in enumerate(wrapped_lines):
                draw.text(
                    (value_x, current_y + line_index * line_spacing),
                    line,
                    font=value_font,
                    fill=self.VALUE_COLOR,
                )
            block_height = max(line_height, len(wrapped_lines) * line_spacing)
            current_y += block_height

    def _estimate_section_height(self, rows: Iterable[tuple[str, str]], value_font, line_height: int = 56) -> int:
        total_height = 0
        scratch = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)

        for _label, value in rows:
            wrapped = self._wrap_text(draw, str(value), value_font, 1020)
            block_height = max(line_height, len(wrapped) * 40)
            total_height += block_height

        return 108 + total_height + 26

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
        if not text:
            return [""]

        lines = []
        current = ""
        for char in text:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            text_width = bbox[2] - bbox[0]
            if current and text_width > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate

        if current:
            lines.append(current)

        return lines[:3]

    def _draw_glow_title(self, draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font, fill: str):
        x, y = position
        glow_color = ImageColor.getrgb("#76561B")
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3)]:
            draw.text((x + dx, y + dy), text, font=font, fill=glow_color)
        draw.text((x, y), text, font=font, fill=fill)

    def _get_font(self, size: int, bold: bool = False):
        for path in self._candidate_fonts(bold):
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _candidate_fonts(self, bold: bool) -> Iterable[Path]:
        local_fonts = [
            self.assets_dir / "fonts" / "font.ttf",
            self.assets_dir / "fonts" / "font.ttc",
            self.assets_dir / "font.ttf",
            self.assets_dir / "font.ttc",
        ]
        for path in local_fonts:
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
