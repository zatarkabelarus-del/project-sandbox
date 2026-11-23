import json
from typing import Any
from agents.providers.factory import get_ai_provider
from core.config import CONFIGS_DIR


class SceneDesigner:
    """Агент 3: Генератор чистого фонового слоя (предметная студия или лайфстайл-сцена)."""

    def __init__(self) -> None:
        prompts_path = CONFIGS_DIR / "prompts" / "agents_prompts.json"
        with prompts_path.open("r", encoding="utf-8") as f:
            self.config = json.load(f).get("scene_designer", {})

    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
        image_model: str | None = None,
        environment_hint: str = "modern clean commercial interior",
    ) -> dict[str, Any]:
        provider = get_ai_provider()
        template_key = "lifestyle_template" if mode == "lifestyle" else "studio_template"
        prompt_template = self.config.get(template_key, "")
        rendered_prompt = prompt_template.format(
            air_zone="top and bottom margins",
            environment_hint=environment_hint,
        )

        result = await provider.generate_background(
            product_id=product_id,
            style_archetype=style_archetype,
            mode=mode,
            bbox=bbox or [0.22, 0.20, 0.56, 0.60],
            image_model=image_model,
            environment_hint=environment_hint,
        )

        if not result.get("background_layer_url"):
            bg_url = str(result.get("background_url") or "")
            bg_b64 = str(result.get("background_base64") or "")
            if bg_url:
                result["background_layer_url"] = bg_url
            elif bg_b64:
                result["background_layer_url"] = f"data:image/jpeg;base64,{bg_b64}"
        result["scene_prompt_used"] = rendered_prompt
        return result

