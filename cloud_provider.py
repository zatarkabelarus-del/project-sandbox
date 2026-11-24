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
        vision_model: str = "gemini-2.5-flash",
        text_model: str = "gemini-2.5-flash",
        image_model: str | None = None,
        budget_limiter: BudgetLimiter | None = None,
        timeout: float = 45.0,
    ) -> None:
        settings = get_settings()
        catalog_default = load_models_catalog().get("default_model", "gemini-nano-banana-2.1")
        default_aiai = "https://" + "api." + "aiai.by" + "/v1"
        env_url = settings.cloud_api_url or os.getenv("CLOUD_API_URL", "")
        raw_url = (gateway_url or env_url or default_aiai).strip().rstrip("/")
        if "aiai.by" in raw_url and not raw_url.endswith("/v1"):
            raw_url = default_aiai
        self.gateway_url = raw_url
        self.vision_model = settings.cloud_vision_model or os.getenv("CLOUD_VISION_MODEL", vision_model)
        self.text_model = settings.cloud_text_model or os.getenv("CLOUD_TEXT_MODEL", text_model)
        self.image_model = image_model or settings.cloud_image_model or os.getenv("CLOUD_IMAGE_MODEL", catalog_default)
        self.budget = budget_limiter or BudgetLimiter(daily_limit_usd=settings.daily_budget_limit_usd)
        self.timeout = timeout

        if encrypted_api_key:
            vault = SecretVault(settings.master_key)
            self._api_key = vault.decrypt_secret(encrypted_api_key)
        else:
            self._api_key = api_key or settings.cloud_api_key or os.getenv("CLOUD_API_KEY", "")

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
    def _shrink_image_bytes_to_data_url(raw_bytes: bytes, max_dim: int = 768, quality: int = 82) -> str:
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        if max(img.size) > max_dim:
            img = ImageOps.contain(img, (max_dim, max_dim), method=Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64_data}"

    @classmethod
    def _prepare_image_bytes(cls, image_url: Any, max_dim: int = 1024) -> bytes | None:
        norm = cls._normalize_image_input(image_url)
        if not norm:
            return None
        if norm.startswith("data:image/") and "," in norm:
            try:
                raw_bytes = base64.b64decode(norm.split(",", 1).pop())
                img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw_bytes))).convert("RGB")
                if max(img.size) > max_dim:
                    img = ImageOps.contain(img, (max_dim, max_dim), method=Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=88, optimize=True)
                return buf.getvalue()
            except Exception:
                return None
        return None

    async def _post_image_edit_multipart(
        self,
        model: str,
        prompt: str,
        image_bytes: bytes,
        size: str = "1024x1024",
    ) -> dict[str, Any]:
        url = f"{self.gateway_url}/images/edits"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"image": ("product.jpg", image_bytes, "image/jpeg")}
        data = {"model": model, "prompt": prompt, "size": size}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            return resp.json()

    async def _resolve_generated_image(self, raw: dict[str, Any]) -> tuple[str, str]:
        data_list = raw.get("data")
        if isinstance(data_list, list) and data_list:
            first_item = next(iter(data_list), {})
            bg_b64 = str(first_item.get("b64_json", "") or "")
            bg_url = str(first_item.get("url", "") or "")
            if not bg_b64 and bg_url.startswith(("http://", "https://")):
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    img_resp = await client.get(bg_url)
                    if img_resp.status_code == 200:
                        bg_b64 = base64.b64encode(img_resp.content).decode("ascii")
            if bg_b64 and not bg_url.startswith("data:image/"):
                bg_url = f"data:image/jpeg;base64,{bg_b64}"
            if bg_url:
                return bg_b64, bg_url

        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            msg = (next(iter(choices), {}) or {}).get("message", {}) or {}
            images_field = msg.get("images")
            if isinstance(images_field, list) and images_field:
                first_img = next(iter(images_field), {})
                img_url = str((first_img.get("image_url") or {}).get("url") or first_img.get("url") or "")
                if img_url.startswith("data:image/") and "," in img_url:
                    return img_url.split(",", 1).pop(), img_url
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        u = str((part.get("image_url") or {}).get("url") or "")
                        if u.startswith("data:image/") and "," in u:
                            return u.split(",", 1).pop(), u
            elif isinstance(content, str):
                m_data = re.search(r"(data:image/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=]+)", content)
                if m_data:
                    u = m_data.group(1)
                    return u.split(",", 1).pop(), u
                m_http = re.search(r"https?://[^\s)\"'>]+", content, re.I)
                if m_http:
                    http_u = m_http.group(0).rstrip(".,;)")
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        r = await client.get(http_u)
                        if r.status_code == 200 and r.content:
                            b64 = base64.b64encode(r.content).decode("ascii")
                            return b64, f"data:image/jpeg;base64,{b64}"
        print(f"[CLOUD_API IMAGE PARSE MISS] raw keys={list(raw.keys())}, sample={str(raw)[:400]}")
        return "", ""

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
        clean_title = str(title or "").strip()
        title_hint = (
            f"User-provided title/notes: '{clean_title}'."
            if clean_title and clean_title.lower() not in ("новый товар", "new product")
            else "No title provided by user — determine the exact product strictly from the attached image."
        )
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": f"{title_hint} (SKU/ID: {product_id}), target lang={lang}. Return valid JSON only."}
        ]
        if norm_img.startswith(("http://", "https://", "data:image/")):
            user_content.append({"type": "image_url", "image_url": {"url": norm_img}})

        vision_prompt = (
            "You are a senior Ozon & Wildberries infographic art director. Look carefully at the product image (PRIMARY source of truth) and optional user notes. "
            "1) Identify the exact product, materials, harmonious brand accent color, and an ideal crisp commercial studio/lifestyle backdrop (WITHOUT the product). "
            "2) Detect the tight product bounding box detected_bbox [x, y, w, h] (normalized 0..1). "
            "3) Find 3 to 4 non-overlapping empty negative-space zones free_zones around the product where infographic badges can be placed WITHOUT touching a single pixel of the product (e.g. top-left, top-right, middle-left, middle-right, bottom-left, bottom-right). Each zone is [x, y, w, h] in 0..1 with w >= 0.28 and h >= 0.08. "
            "NEVER invent unrelated demo gadgets or placeholder names. "
            "Return ONLY raw JSON object (no markdown) with keys: "
            "detected_product_name (string, exact name in target language), "
            "visual_scene_idea (string in English, vivid crisp empty commercial backdrop description for this item, NO blur/bokeh), "
            "detected_bbox (list of 4 floats 0..1), "
            "free_zones (list of 3-4 lists [x, y, w, h] in 0..1 strictly outside detected_bbox), "
            "accent_color (hex string like '#2563EB' or '#EA580C' matching the product), "
            "dominant_colors (list of 2-3 hex colors), "
            "key_features (list of 4-6 short factual product benefits in target language)."
        )
        payload = {
            "model": self.vision_model,
            "temperature": 0.25,
            "messages": [
                {"role": "system", "content": vision_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            raw = await self._post_with_retry("/chat/completions", payload)
        except AIProviderNetworkError:
            fallback_hint = clean_title or f"Commercial product ({product_id})"
            text_only_payload = {
                "model": self.text_model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": vision_prompt},
                    {
                        "role": "user",
                        "content": f"Analyze product '{fallback_hint}' (ID: {product_id}), lang={lang}. Return valid JSON only.",
                    },
                ],
            }
            raw = await self._post_with_retry("/chat/completions", text_only_payload)
        parsed = self._extract_json_content(raw)
        fallback_name = clean_title or "Товар каталога"
        raw_zones = parsed.get("free_zones")
        valid_zones = [
            [round(float(c), 4) for c in z[:4]]
            for z in (raw_zones if isinstance(raw_zones, list) else [])
            if isinstance(z, list) and len(z) >= 4
        ]
        return {
            "product_id": product_id,
            "vision_enabled": True,
            "detected_product_name": str(parsed.get("detected_product_name") or fallback_name).strip(),
            "visual_scene_idea": str(parsed.get("visual_scene_idea") or "").strip(),
            "detected_bbox": parsed.get("detected_bbox", [0.26, 0.22, 0.48, 0.54]),
            "free_zones": valid_zones,
            "accent_color": str(parsed.get("accent_color") or "#2563EB").strip(),
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
        target_lang = "Russian" if str(lang).lower().startswith("ru") else "English"
        payload = {
            "model": self.text_model,
            "temperature": 0.35,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a senior Ozon & Wildberries conversion copywriter. Output language: {target_lang}. "
                        f"Write strictly factual, concrete, high-value buyer benefits, technical specs, materials, compatibility, and practical use cases ONLY for the exact product provided in 'title' and 'attributes'. "
                        f"NEVER invent unrelated properties, NEVER use vague filler ('высокое качество', 'надёжный выбор', 'идеальное решение'), and NEVER repeat the same thesis across slides. "
                        f"Keep headlines crisp (2-4 words, max 32 chars), subheadlines max 44 chars, "
                        f"and provide 2-3 ultra-short infographic callouts in 'pills' (1-3 words, max 20 chars each). "
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
                            "user_short_description": attributes.get("short_description", ""),
                            "user_full_description": attributes.get("full_description", ""),
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
        source_image_url: str = "",
    ) -> dict[str, Any]:
        self.budget.check_and_consume("generate_background", self.OP_COSTS_USD["generate_background"])
        safe_bbox = bbox or [0.2, 0.22, 0.8, 0.78]
        active_model = image_model or self.image_model
        model_lower = active_model.lower()
        clean_hint = str(environment_hint or "").strip()

        bg_b64 = ""
        bg_url = ""
        scene_includes_product = False

        # Если передан готовый кадр (Чистый фон + Python-товар со светом и тенью),
        # накладываем ТОЛЬКО дизайнерскую инфографику со строгим запретом на сдвиг и цветокоррекцию
        src_bytes = self._prepare_image_bytes(source_image_url, max_dim=1024) if source_image_url else None
        user_prompt_body = clean_hint.replace("[PRESERVE_BG_AND_PRODUCT]", "").strip()
        if src_bytes:
            src_data_url = f"data:image/jpeg;base64,{base64.b64encode(src_bytes).decode('ascii')}"
            designer_prompt = (
                "STRICT IN-PLACE EDIT: Do NOT shift, move, resize, crop, re-render, or apply color grading/filters to the product or the background from the input image. "
                "Every pixel of the product and background must remain in its exact original position and original color. "
                "Act as an experienced Ozon & Wildberries art director: first evaluate the product category, target audience, and visual mood from the image and text (e.g., industrial/automotive spare parts need strict technical callout lines, clean geometric plates, and functional icons; perfumes & luxury goods need refined minimalist typography and soft accents; kids' toys & gifts suit bright playful badges, stars, and ribbons; home & apparel suit warm lifestyle cards). "
                "Add ONLY high-converting marketplace infographic elements whose style, palette, and shapes authentically match THIS specific product category, placed strictly in empty areas around the product without covering it: "
                f"{user_prompt_body}."
            )

            is_gemini_or_gpt = any(k in model_lower for k in ("gemini", "nano-banana", "gpt-image"))
            if is_gemini_or_gpt:
                chat_payload: dict[str, Any] = {
                    "model": active_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": designer_prompt},
                                {"type": "image_url", "image_url": {"url": src_data_url}},
                            ],
                        }
                    ],
                }
                raw_chat = await self._post_with_retry("/chat/completions", chat_payload)
                bg_b64, bg_url = await self._resolve_generated_image(raw_chat)
            else:
                raw_edit = await self._post_image_edit_multipart(
                    model=active_model,
                    prompt=designer_prompt,
                    image_bytes=src_bytes,
                    size="1024x1024",
                )
                bg_b64, bg_url = await self._resolve_generated_image(raw_edit)

            scene_includes_product = bool(bg_url)
        else:
            # Генерация чистого фона без товара и текста (когда src_bytes не передан)
            fallback_prompt = (
                f"Sharp, high-resolution commercial e-commerce {mode} product photography backdrop, style {style_archetype}. "
                f"{user_prompt_body}. "
                f"Clean open composition with natural studio depth. CRITICAL: Completely EMPTY scene — NO product, NO object, NO text, NO letters, NO watermarks."
            )
            raw = await self._post_with_retry(
                "/images/generations",
                {"model": active_model, "prompt": fallback_prompt, "size": "1024x1024"},
            )
            bg_b64, bg_url = await self._resolve_generated_image(raw)
            scene_includes_product = False

        return {
            "product_id": product_id,
            "style_archetype": style_archetype,
            "mode": mode,
            "image_model": active_model,
            "safe_bbox": safe_bbox,
            "scene_includes_product": scene_includes_product,
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
