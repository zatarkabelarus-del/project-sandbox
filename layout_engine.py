import copy
import json
import math
from typing import Any
from core.config import CONFIGS_DIR
from graphics.image_utils import calculate_bbox_iou_and_overlap


class LayoutEngine:
    """
    Агент 4: Auto-Layout векторного слоя инфографики поверх чистого растрового фона.
    Поддерживает фиксацию стиля плашек (lock_plate_style) с эластичной подгонкой
    высоты под длину текста без перекрытия BBox товара.
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
    @staticmethod
    def _normalize_box(layer: dict[str, Any], canvas_w: float, canvas_h: float) -> list[float]:
        if isinstance(layer.get("bbox"), list) and len(layer["bbox"]) == 4:
            return [float(v) for v in layer["bbox"]]
        w_base = max(1.0, float(canvas_w))
        h_base = max(1.0, float(canvas_h))
        x = max(0.0, min(0.95, float(layer.get("x", 40)) / w_base))
        y = max(0.0, min(0.95, float(layer.get("y", 40)) / h_base))
        w = max(0.05, min(1.0 - x, float(layer.get("width", 300)) / w_base))
        h = max(0.03, min(1.0 - y, float(layer.get("height", 60)) / h_base))
        return [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]
    @staticmethod
    def _fit_plate_to_text(
        base_box: list[float],
        text: str,
        base_font_size: int,
        product_bbox: list[float],
    ) -> tuple[list[float], int]:
        x, y, w, base_h = base_box
        clean_len = max(1, len((text or "").strip()))
        chars_per_line = max(12, int((w * 1080) / max(10.0, base_font_size * 0.56)))
        lines_needed = max(1, math.ceil(clean_len / chars_per_line))
        desired_h = max(base_h, min(0.32, (lines_needed * base_font_size * 1.42 + 24) / 1440.0))
        is_bottom = (y + base_h * 0.5) >= 0.52
        candidate_y = max(0.02, min(0.98 - desired_h, (y + base_h - desired_h) if is_bottom else y))
        candidate_box = [round(x, 4), round(candidate_y, 4), round(w, 4), round(desired_h, 4)]
        font_size = base_font_size
        while calculate_bbox_iou_and_overlap(candidate_box, product_bbox) > 0.05 and desired_h > base_h:
            desired_h = max(base_h, desired_h * 0.88)
            font_size = max(int(base_font_size * 0.75), font_size - 2)
            candidate_y = max(0.02, min(0.98 - desired_h, (y + base_h - desired_h) if is_bottom else y))
            candidate_box = [round(x, 4), round(candidate_y, 4), round(w, 4), round(desired_h, 4)]
        return candidate_box, font_size
    def _build_layers_from_pilot_slide(
        self,
        pilot_slide: dict[str, Any],
        slide_data: dict[str, Any],
        product_bbox: list[float],
        canvas_w: float,
        canvas_h: float,
        lock_plate_style: bool,
    ) -> list[dict[str, Any]]:
        built: list[dict[str, Any]] = []
        headline = slide_data.get("headline", "")
        subheadline = slide_data.get("subheadline", "")
        for idx, raw in enumerate(pilot_slide.get("layers", [])):
            ltype = str(raw.get("type", "badge"))
            lid = str(raw.get("id", f"layer-{idx}"))
            base_box = self._normalize_box(raw, canvas_w, canvas_h)
            base_font = int(raw.get("fontSize") or raw.get("font_size") or 22)
            fill = raw.get("bgColor") or raw.get("fill") or "#0F172A"
            color = raw.get("textColor") or raw.get("color") or "#FFFFFF"
            radius = int(raw.get("borderRadius") or raw.get("corner_radius") or 12)
            opacity = float(raw.get("opacity", 0.94))

            if ltype in ("title", "headline_text") or lid == "headline_text":
                text_val = headline or str(raw.get("text", ""))
                box, f_size = self._fit_plate_to_text(base_box, text_val, base_font, product_bbox) if lock_plate_style else (base_box, base_font)
            elif ltype in ("subtitle", "subheadline_text", "feature_box") or lid == "subheadline_text":
                text_val = subheadline or str(raw.get("text", ""))
                box, f_size = self._fit_plate_to_text(base_box, text_val, base_font, product_bbox) if lock_plate_style else (base_box, base_font)
            else:
                text_val = str(raw.get("text", ""))
                box, f_size = base_box, base_font

            built.append({"id": f"{lid}_plate", "type": "rect", "bbox": box, "fill": fill, "opacity": opacity, "corner_radius": radius})
            t_box = [round(box[0] + 0.015, 4), round(box[1] + 0.01, 4), round(max(0.02, box[2] - 0.03), 4), round(max(0.02, box[3] - 0.02), 4)]
            built.append({"id": lid, "type": "text", "bbox": t_box, "text": text_val, "font_family": raw.get("font_family", "Inter"), "font_size": f_size, "color": color, "bg_reference": fill})
        return built
    def compose_layers(
        self,
        slide_data: dict[str, Any],
        background_data: dict[str, Any],
        product_bbox: list[float],
        style_code: str = "minimal_light",
        style_passport: dict[str, Any] | None = None,
        approved_master_schema: dict[str, Any] | None = None,
        lock_plate_style: bool = True,
    ) -> dict[str, Any]:
        passport = self._get_style_passport(style_code, style_passport)
        palette = passport.get("palette", {})
        typography = passport.get("typography", {})
        geometry = passport.get("geometry", {})
        slide_idx = int(slide_data.get("slide_index", 1))
        bg_url = background_data.get("background_layer_url", "")
        if approved_master_schema and isinstance(approved_master_schema.get("slides"), list) and approved_master_schema["slides"]:
            use_lock = bool(approved_master_schema.get("lock_plate_style", lock_plate_style))
            c_base = approved_master_schema.get("canvas_base") or {"width": 800, "height": 800}
            slides_list = approved_master_schema["slides"]
            pilot_slide = next((s for s in slides_list if int(s.get("slideIndex", 0)) == slide_idx), slides_list[0])
            layers = self._build_layers_from_pilot_slide(
                pilot_slide=pilot_slide,
                slide_data=slide_data,
                product_bbox=product_bbox,
                canvas_w=float(c_base.get("width", 800)),
                canvas_h=float(c_base.get("height", 800)),
                lock_plate_style=use_lock,
            )
            if layers:
                return {
                    "canvas": {"width": self.BASE_WIDTH, "height": self.BASE_HEIGHT, "coord_system": "normalized"},
                    "slide_index": slide_idx,
                    "style_code": style_code,
                    "background_url": bg_url,
                    "product_bbox": product_bbox,
                    "layers": layers,
                }
        if approved_master_schema and approved_master_schema.get("layers"):
            schema = copy.deepcopy(approved_master_schema)
            schema["slide_index"] = slide_idx
            schema["background_url"] = bg_url
            for layer in schema["layers"]:
                if layer.get("id") == "headline_text":
                    layer["text"] = slide_data.get("headline", "")
                elif layer.get("id") == "subheadline_text":
                    layer["text"] = slide_data.get("subheadline", "")
            return schema
        header_box = [0.06, 0.04, 0.88, 0.13]
        footer_box = [0.06, 0.82, 0.88, 0.13]
        if calculate_bbox_iou_and_overlap(header_box, product_bbox) > 0.05:
            header_box = [0.06, 0.72, 0.88, 0.11]
            footer_box = [0.06, 0.85, 0.88, 0.11]

        layers = [
            {"id": "header_badge", "type": "rect", "bbox": header_box, "fill": palette.get("surface_card", "#FFFFFF"), "opacity": palette.get("surface_alpha", 0.92), "corner_radius": geometry.get("border_radius", 16)},
            {"id": "headline_text", "type": "text", "bbox": [header_box[0] + 0.03, header_box[1] + 0.025, header_box[2] - 0.06, header_box[3] - 0.05], "text": slide_data.get("headline", ""), "font_family": typography.get("heading_font", "Inter"), "font_size": typography.get("heading_size", 44), "color": palette.get("text_primary", "#0F172A"), "bg_reference": palette.get("surface_card", "#FFFFFF")},
            {"id": "footer_badge", "type": "rect", "bbox": footer_box, "fill": palette.get("accent", "#2563EB"), "opacity": 0.95, "corner_radius": geometry.get("border_radius", 16)},
            {"id": "subheadline_text", "type": "text", "bbox": [footer_box[0] + 0.03, footer_box[1] + 0.03, footer_box[2] - 0.06, footer_box[3] - 0.06], "text": slide_data.get("subheadline", ""), "font_family": typography.get("body_font", "Inter"), "font_size": typography.get("body_size", 24), "color": palette.get("accent_text", "#FFFFFF"), "bg_reference": palette.get("accent", "#2563EB")},
        ]
        return {"canvas": {"width": self.BASE_WIDTH, "height": self.BASE_HEIGHT, "coord_system": "normalized"}, "slide_index": slide_idx, "style_code": style_code, "background_url": bg_url, "product_bbox": product_bbox, "layers": layers}
