import asyncio
import base64
import io
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
import httpx
from PIL import Image, ImageOps

from agents.providers.base_provider import AIProviderAdapter
from core.budget_limiter import BudgetLimiter
from core.config import get_settings, load_models_catalog
from core.exceptions import AIContentValidationError, AIProviderNetworkError
from core.security import SecretVault


class CloudAPIProvider(AIProviderAdapter):
    """Адаптер облачных ИИ-шлюзов (CLOUD_API) с контролем бюджета и AES-256 ключами."""

    provider_name: str = "cloud_api"

    OP_COSTS_USD: dict[str, float] = {
        "analyze_product": 0.015,
        "build_funnel_and_seo": 0.025,
        "generate_background": 0.040,
        "validate_slide": 0.010,
    }

    def __init__(
        self,
        api_key: str | None = None,
        encrypted_api_key: str | None = None,
        gateway_url: str | None = None,
        vision_model: str = "gpt-4o-mini",
        text_model: str = "gpt-4o-mini",
        image_model: str | None = None,
        budget_limiter: BudgetLimiter | None = None,
        timeout: float = 45.0,
    ) -> None:
        settings = get_settings()
        catalog_default = load_models_catalog().get("default_model", "gemini-nano-banana-2.1")
        default_aiai = "https://" + "api." + "aiai.by" + "/v1"
        raw_url = (gateway_url or os.getenv("CLOUD_API_URL", default_aiai)).strip().rstrip("/")
        if "aiai.by" in raw_url and not raw_url.endswith("/v1"):
            raw_url = default_aiai
        self.gateway_url = raw_url
        self.vision_model = os.getenv("CLOUD_VISION_MODEL", vision_model)
        self.text_model = os.getenv("CLOUD_TEXT_MODEL", text_model)
        self.image_model = image_model or os.getenv("CLOUD_IMAGE_MODEL", catalog_default)
        self.budget = budget_limiter or BudgetLimiter(daily_limit_usd=settings.daily_budget_limit_usd)
        self.timeout = timeout

        if encrypted_api_key:
            vault = SecretVault(settings.master_key)
            self._api_key = vault.decrypt_secret(encrypted_api_key)
        else:
            self._api_key = api_key or os.getenv("CLOUD_API_KEY", "")

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIProviderNetworkError("CLOUD_API key is missing in SecretVault or environment")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post_with_retry(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.gateway_url}/{endpoint.lstrip('/')}"
        delays = [2, 4, 8]
        last_exc: Exception | None = None

        for attempt in range(len(delays) + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                body_preview = exc.response.text[:300] if exc.response is not None else ""
                if exc.response is not None and exc.response.status_code in (400, 401, 403, 404):
                    raise AIProviderNetworkError(
                        f"Cloud API HTTP {exc.response.status_code} ({url}): {body_preview}"
                    ) from exc
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])

        raise AIProviderNetworkError(f"Cloud API request failed after retries: {last_exc}") from last_exc

    @staticmethod
    def _extract_json_content(raw_response: dict[str, Any]) -> dict[str, Any]:
        try:
            first_choice = next(iter(raw_response["choices"]))
            content = str(first_choice["message"]["content"]).strip()
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
        except (KeyError, StopIteration, TypeError, json.JSONDecodeError) as exc:
            raise AIContentValidationError(f"Invalid JSON structure from Cloud API: {exc}") from exc

    @staticmethod
    def _shrink_image_bytes_to_data_url(raw_bytes: bytes) -> str:
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        if max(img.size) > 768:
            img = ImageOps.contain(img, (768, 768), method=Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64_data}"

    @classmethod
    def _normalize_image_input(cls, image_url: Any) -> str:
        if isinstance(image_url, list):
            image_url = next(iter(image_url), "")
        url_str = str(image_url or "").strip()
        if not url_str or url_str.startswith(("http://", "https://")):
            return url_str
        if url_str.startswith("data:image/") and "," in url_str:
            try:
                raw_bytes = base64.b64decode(url_str.split(",", 1).pop())
                return cls._shrink_image_bytes_to_data_url(raw_bytes)
            except Exception:
                return url_str
        clean_path = url_str.lstrip("/")
        project_root = Path(__file__).resolve().parents[3]
        candidates = [Path(url_str), Path.cwd() / clean_path, project_root / clean_path]
        for path_obj in candidates:
            if path_obj.is_file():
                return cls._shrink_image_bytes_to_data_url(path_obj.read_bytes())
        return url_str

    async def analyze_product(
        self,
        product_id: str,
        title: str,
        image_url: str,
        enable_vision: bool = True,
        lang: str = "ru",
    ) -> dict[str, Any]:
        if not enable_vision:
            return {
                "product_id": product_id,
                "vision_enabled": False,
                "detected_bbox": [0.2, 0.22, 0.8, 0.78],
                "dominant_colors": ["#F5F5F5", "#222222"],
                "key_features": [title],
            }

        self.budget.check_and_consume("analyze_product", self.OP_COSTS_USD["analyze_product"])
        norm_img = self._normalize_image_input(image_url)
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": f"Analyze product '{title}' (ID: {product_id}), lang={lang}. Return valid JSON only."}
        ]
        if norm_img.startswith(("http://", "https://", "data:image/")):
            user_content.append({"type": "image_url", "image_url": {"url": norm_img}})

        vision_prompt = (
            "You are an expert e-commerce art director. Look carefully at the product image (if provided) and title. "
            "Identify what exact object is shown on the photo, its category, materials, target audience, harmonious brand colors, "
            "and design an ideal crisp studio/lifestyle backdrop idea specifically for THIS product. "
            "Return ONLY raw JSON object (no markdown) with keys: "
            "detected_product_name (string, exact name of the object seen in the image in target language), "
            "visual_scene_idea (string in English, vivid crisp commercial photography backdrop description for this specific item, NO blur/bokeh), "
            "detected_bbox (list of 4 floats 0..1), "
            "dominant_colors (list of 2-3 hex colors), "
            "key_features (list of 4-6 short factual product benefits in target language)."
        )
        payload = {
            "model": self.vision_model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": vision_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            raw = await self._post_with_retry("/chat/completions", payload)
        except AIProviderNetworkError:
            text_only_payload = {
                "model": self.text_model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": vision_prompt},
                    {
                        "role": "user",
                        "content": f"Analyze product '{title}' (ID: {product_id}), lang={lang}. Return valid JSON only.",
                    },
                ],
            }
            raw = await self._post_with_retry("/chat/completions", text_only_payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "vision_enabled": True,
            "detected_product_name": str(parsed.get("detected_product_name") or title).strip(),
            "visual_scene_idea": str(parsed.get("visual_scene_idea") or "").strip(),
            "detected_bbox": parsed.get("detected_bbox", [0.24, 0.23, 0.52, 0.49]),
            "dominant_colors": parsed.get("dominant_colors", ["#0f172a", "#2563eb"]),
            "key_features": parsed.get("key_features", [title]),
        }

    async def build_funnel_and_seo(
        self,
        product_id: str,
        title: str,
        attributes: dict[str, Any],
        slides_count: int = 5,
        avoid_title_duplication: bool = False,
        lang: str = "ru",
    ) -> dict[str, Any]:
        self.budget.check_and_consume("build_funnel_and_seo", self.OP_COSTS_USD["build_funnel_and_seo"])
        safe_count = max(1, min(8, int(slides_count)))
        dup_rule = (
            " Do NOT repeat or duplicate the full product title on slide headlines or badges; put only benefits and specs."
            if avoid_title_duplication
            else ""
        )
        payload = {
            "model": self.text_model,
            "temperature": 0.55,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a top Ozon & Wildberries marketplace infographic copywriter. "
                        f"Create high-converting, punchy, concise copy tailored strictly to the real product described in attributes/vision. "
                        f"NEVER use generic filler phrases. Keep headlines short (max 34 chars), subheadlines max 44 chars, "
                        f"and provide 2-3 compact pill-badges per slide (max 24 chars each, e.g. '⚡ Нагрузка 5–60 кг', '🛡 Стальная пружина'). "
                        f"Return ONLY raw JSON with keys: slides (exact list of {safe_count} objects with slide_index, role, headline, subheadline, badge, pills (list of 2-3 short strings)), "
                        f"rich_content_html (isolated div without global styles), seo (meta_title, meta_description, slug).{dup_rule}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "product_id": product_id,
                            "title": title,
                            "attributes": attributes,
                            "slides_count": safe_count,
                            "avoid_title_duplication": avoid_title_duplication,
                            "lang": lang,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        raw = await self._post_with_retry("/chat/completions", payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "slides": parsed.get("slides", []),
            "avoid_title_duplication": avoid_title_duplication,
            "rich_content_html": parsed.get("rich_content_html", f"<div class='ai-rich-block'><h2>{title}</h2></div>"),
            "seo": parsed.get("seo", {"meta_title": title, "meta_description": title, "slug": product_id.lower()}),
        }

    async def generate_background(
        self,
        product_id: str,
        style_archetype: str,
        mode: str = "studio",
        bbox: list[float] | None = None,
        image_model: str | None = None,
        environment_hint: str = "",
    ) -> dict[str, Any]:
        self.budget.check_and_consume("generate_background", self.OP_COSTS_USD["generate_background"])
        safe_bbox = bbox or [0.2, 0.22, 0.8, 0.78]
        active_model = image_model or self.image_model
        scene_desc = f"Scene concept tailored to product: {environment_hint}. " if environment_hint else ""
        payload = {
            "model": active_model,
            "prompt": (
                f"Sharp, high-resolution commercial e-commerce {mode} product photography backdrop, style {style_archetype}. "
                f"{scene_desc}"
                f"Crisp architectural surface with studio rim lighting and soft contact shadow in the center, "
                f"clean open composition with breathing room at top and bottom margins for infographic badges. "
                f"CRITICAL: Completely EMPTY center — NO product, NO object, NO item, NO text, NO letters, NO watermarks, NO heavy blur."
            ),
            "size": "1024x1024",
        }

        raw = await self._post_with_retry("/images/generations", payload)
        data_list = raw.get("data") or [{}]
        first_item = next(iter(data_list), {}) if isinstance(data_list, list) else {}
        bg_b64 = str(first_item.get("b64_json", "") or "")
        bg_url = str(first_item.get("url", "") or "")
        if not bg_b64 and bg_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                img_resp = await client.get(bg_url)
                if img_resp.status_code == 200:
                    bg_b64 = base64.b64encode(img_resp.content).decode("ascii")
        if bg_b64 and not bg_url.startswith("data:image/"):
            bg_url = f"data:image/jpeg;base64,{bg_b64}"
        return {
            "product_id": product_id,
            "style_archetype": style_archetype,
            "mode": mode,
            "image_model": active_model,
            "safe_bbox": safe_bbox,
            "background_base64": bg_b64,
            "background_url": bg_url,
        }

    async def validate_slide(
        self,
        product_id: str,
        slide_index: int,
        layout_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.budget.check_and_consume("validate_slide", self.OP_COSTS_USD["validate_slide"])
        compact_schema = {
            k: ("[data_image_present]" if isinstance(v, str) and v.startswith("data:image/") else v)
            for k, v in layout_schema.items()
        }
        payload = {
            "model": self.text_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": "Audit slide layout JSON. Return ONLY raw JSON object with keys: passed (bool), score (float 0..1), issues (list of strings).",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"product_id": product_id, "slide_index": slide_index, "layout_schema": compact_schema},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        raw = await self._post_with_retry("/chat/completions", payload)
        parsed = self._extract_json_content(raw)
        return {
            "product_id": product_id,
            "slide_index": slide_index,
            "passed": bool(parsed.get("passed", True)),
            "score": float(parsed.get("score", 0.95)),
            "issues": parsed.get("issues", []),
        }
