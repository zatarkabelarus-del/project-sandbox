import json
from typing import Any
from agents.providers.factory import get_ai_provider
from core.config import CONFIGS_DIR
from graphics.image_utils import calculate_bbox_iou_and_overlap, calculate_wcag_contrast


class CriticAgent:
    """Агент 5: Vision- и геометрический валидатор качества макета перед публикацией."""

    def __init__(self) -> None:
        prompts_path = CONFIGS_DIR / "prompts" / "agents_prompts.json"
        with prompts_path.open("r", encoding="utf-8") as f:
            self.config = json.load(f).get("critic", {})

    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        issues: list[str] = []
        product_bbox = layout_schema.get("product_bbox", [0.22, 0.20, 0.56, 0.60])
        min_contrast = float(self.config.get("min_contrast_ratio", 4.5))
        max_overlap = float(self.config.get("max_overlap_ratio", 0.05))

        for layer in layout_schema.get("layers", []):
            layer_bbox = layer.get("bbox")
            if layer_bbox:
                overlap = calculate_bbox_iou_and_overlap(layer_bbox, product_bbox)
                if overlap > max_overlap:
                    issues.append(f"Layer '{layer.get('id')}' overlaps product bbox ({overlap:.2f} > {max_overlap})")

            if layer.get("type") == "text":
                fg = layer.get("color", "#0F172A")
                bg = layer.get("bg_reference", "#FFFFFF")
                contrast = calculate_wcag_contrast(fg, bg)
                if contrast < min_contrast:
                    issues.append(f"Low WCAG contrast on '{layer.get('id')}': {contrast} < {min_contrast}")

        provider = get_ai_provider()
        provider_report = await provider.validate_slide(
            product_id=product_id,
            slide_index=slide_index,
            layout_schema=layout_schema,
        )

        all_issues = issues + provider_report.get("issues", [])
        return {
            "product_id": product_id,
            "slide_index": slide_index,
            "passed": len(all_issues) == 0 and provider_report.get("passed", True),
            "issues": all_issues,
            "estimated_cost_usd": provider_report.get("estimated_cost_usd", 0.0),
        }
