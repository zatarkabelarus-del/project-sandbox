import copy
import json
from typing import Any
from core.config import CONFIGS_DIR
from graphics.image_utils import calculate_bbox_iou_and_overlap


class LayoutEngine:
    """
    Агент 4: Auto-Layout векторного слоя инфографики поверх чистого растрового фона.
    Работает в нормализованных координатах (0.0..1.0) с базовым холстом 1080x1440.
    """

    BASE_WIDTH = 1080
    BASE_HEIGHT = 1440

    def __init__(self) -> None:
        styles_path = CONFIGS_DIR / "styles" / "base_archetypes.json"
        with styles_path.open("r", encoding="utf-8") as f:
            self.styles_catalog = json.load(f).get("styles", {})

    def _get_style_passport(self, style_code: str, custom_passport: dict[str, Any] | None = None) -> dict[str, Any]:
        if custom_passport:
            return custom_passport
        return self.styles_catalog.get(style_code, next(iter(self.styles_catalog.values())))

    def compose_layers(
        self,
        slide_data: dict[str, Any],
        background_data: dict[str, Any],
        product_bbox: list[float],
        style_code: str = "minimal_light",
        style_passport: dict[str, Any] | None = None,
        approved_master_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        passport = self._get_style_passport(style_code, style_passport)
        palette = passport.get("palette", {})
        typography = passport.get("typography", {})
        geometry = passport.get("geometry", {})

        # Если передан утвержденный Мастер-шаблон после ПИЛОТА — наследуем его геометрию слоев
        if approved_master_schema and approved_master_schema.get("layers"):
            schema = copy.deepcopy(approved_master_schema)
            schema["slide_index"] = slide_data.get("slide_index", 1)
            schema["background_url"] = background_data.get("background_layer_url", "")
            for layer in schema["layers"]:
                if layer.get("id") == "headline_text":
                    layer["text"] = slide_data.get("headline", "")
                elif layer.get("id") == "subheadline_text":
                    layer["text"] = slide_data.get("subheadline", "")
            return schema

        # Автоматическая расстановка плашек в безопасных зонах ("воздухе")
        header_box = [0.06, 0.04, 0.88, 0.13]
        footer_box = [0.06, 0.82, 0.88, 0.13]

        if calculate_bbox_iou_and_overlap(header_box, product_bbox) > 0.05:
            header_box = [0.06, 0.72, 0.88, 0.11]
            footer_box = [0.06, 0.85, 0.88, 0.11]

        layers = [
            {
                "id": "header_badge",
                "type": "rect",
                "bbox": header_box,
                "fill": palette.get("surface_card", "#FFFFFF"),
                "opacity": palette.get("surface_alpha", 0.92),
                "corner_radius": geometry.get("border_radius", 16),
            },
            {
                "id": "headline_text",
                "type": "text",
                "bbox": [header_box[0] + 0.03, header_box[1] + 0.025, header_box[2] - 0.06, header_box[3] - 0.05],
                "text": slide_data.get("headline", ""),
                "font_family": typography.get("heading_font", "Inter"),
                "font_size": typography.get("heading_size", 44),
                "color": palette.get("text_primary", "#0F172A"),
                "bg_reference": palette.get("surface_card", "#FFFFFF"),
            },
            {
                "id": "footer_badge",
                "type": "rect",
                "bbox": footer_box,
                "fill": palette.get("accent", "#2563EB"),
                "opacity": 0.95,
                "corner_radius": geometry.get("border_radius", 16),
            },
            {
                "id": "subheadline_text",
                "type": "text",
                "bbox": [footer_box[0] + 0.03, footer_box[1] + 0.03, footer_box[2] - 0.06, footer_box[3] - 0.06],
                "text": slide_data.get("subheadline", ""),
                "font_family": typography.get("body_font", "Inter"),
                "font_size": typography.get("body_size", 24),
                "color": palette.get("accent_text", "#FFFFFF"),
                "bg_reference": palette.get("accent", "#2563EB"),
            },
        ]

        return {
            "canvas": {"width": self.BASE_WIDTH, "height": self.BASE_HEIGHT, "coord_system": "normalized"},
            "slide_index": slide_data.get("slide_index", 1),
            "style_code": style_code,
            "background_url": background_data.get("background_layer_url", ""),
            "product_bbox": product_bbox,
            "layers": layers,
        }
