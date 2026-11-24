import base64
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from connectors.content_protector import compose_protected_descriptions
from connectors.store_service import DEFAULT_STORE_SETTINGS, build_woocommerce_connector
from core.exceptions import CMSConnectorError, PlatformBaseError
from core.fsm import TaskStateMachine, TaskStatus
from core.i18n import translate_status
from database.models import GenerationTask, Product, Store
from database.session import get_db
from graphics.image_utils import encode_image_bytes, resolve_output_format

router = APIRouter(prefix="/api", tags=["publish"])


class WooCommercePublishRequest(BaseModel):
    task_id: int
    store_id: int | None = None
    store_url: str | None = None
    consumer_key: str | None = None
    consumer_secret: str | None = None
    bridge_token: str | None = None
    external_product_id: str | None = None
    short_description_override: str | None = None
    rich_html_override: str | None = None
    video_url: str = ""
    keep_existing_shortcodes: bool | None = None
    description_before_shortcode: bool | None = None
    keep_existing_video: bool | None = None
    description_before_video: bool | None = None
    output_format: str | None = None
    output_quality: int | None = None
    preview_only: bool = True
    lang: str = "ru"


def _build_slide_filename(raw_slug: str | None, sku: str, idx: int, ext: str) -> str:
    base = (raw_slug or f"{sku}-slide-{idx + 1}").strip()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return f"{base}.{ext}"


@router.post("/publish/woocommerce")
async def publish_to_woocommerce(
    request: Request, payload: WooCommercePublishRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    task = (await db.execute(select(GenerationTask).where(GenerationTask.id == payload.task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"GenerationTask {payload.task_id} not found")
    product = (await db.execute(select(Product).where(Product.id == task.product_id))).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {task.product_id} not found")

    target_store_id = payload.store_id or product.store_id
    store = (await db.execute(select(Store).where(Store.id == target_store_id))).scalar_one_or_none() if target_store_id else None
    store_cfg = {**DEFAULT_STORE_SETTINGS, **(store.settings_json if store else {})}

    raw_fmt = payload.output_format or store_cfg.get("output_format", "webp")
    quality = payload.output_quality if payload.output_quality is not None else int(store_cfg.get("output_quality", 90))
    pil_fmt, ext, mime_type = resolve_output_format(raw_fmt)

    ai_short = payload.short_description_override if payload.short_description_override is not None else (task.marketing_funnel or {}).get("short_description", "")
    ai_rich = payload.rich_html_override if payload.rich_html_override is not None else (task.rich_content_html or "")
    protected = compose_protected_descriptions(
        ai_short_description=ai_short,
        ai_rich_html=ai_rich,
        embedded_blocks=product.embedded_blocks,
        short_description_suffix=store_cfg.get("short_description_suffix", ""),
        video_url=payload.video_url,
        keep_existing_shortcodes=payload.keep_existing_shortcodes if payload.keep_existing_shortcodes is not None else store_cfg["keep_existing_shortcodes"],
        description_before_shortcode=payload.description_before_shortcode if payload.description_before_shortcode is not None else store_cfg["description_before_shortcode"],
        keep_existing_video=payload.keep_existing_video if payload.keep_existing_video is not None else store_cfg["keep_existing_video"],
        description_before_video=payload.description_before_video if payload.description_before_video is not None else store_cfg["description_before_video"],
    )

    ext_id = payload.external_product_id or product.external_id or str(product.id)
    slides: list[dict[str, Any]] = task.slides_payload or []
    seo_meta: dict[str, Any] = task.seo_payload or {}

    if payload.preview_only:
        prepared_media = [
            {
                "slide_index": idx + 1,
                "filename_slug": _build_slide_filename(slide.get("seo_filename"), product.sku, idx, ext),
                "format": pil_fmt.lower(),
                "mime_type": mime_type,
                "quality": quality,
                "alt_text": slide.get("alt_text") or f"{product.title} - {idx + 1}",
                "title_text": slide.get("title_text") or product.title,
            }
            for idx, slide in enumerate(slides)
        ]
        return {
            "preview_only": True,
            "task_id": task.id,
            "fsm_status": task.status,
            "fsm_status_label": translate_status(task.status, lang=payload.lang),
            "external_product_id": ext_id,
            "output_format": pil_fmt.lower(),
            "output_quality": quality,
            "media_plan": prepared_media,
            "protected_short_description": protected["short_description"],
            "isolated_rich_html": protected["description"],
            "seo_meta": seo_meta,
        }

    connector = build_woocommerce_connector(
        store,
        request.app.state.vault,
        override_url=payload.store_url,
        override_key=payload.consumer_key,
        override_secret=payload.consumer_secret,
        override_bridge=payload.bridge_token,
    )
    if not connector.base_url or not connector.auth[0] or not connector.auth[1]:
        raise CMSConnectorError("WooCommerce store credentials are required for live publication")

    current_status = TaskStatus(task.status)
    if current_status == TaskStatus.PILOT_REVIEW:
        current_status = TaskStateMachine.transition(current_status, TaskStatus.READY_TO_PUBLISH)
    if current_status == TaskStatus.READY_TO_PUBLISH:
        task.status = TaskStateMachine.transition(current_status, TaskStatus.UPLOADING).value
        await db.commit()

    try:
        uploaded_media_ids: list[int | str] = []
        for idx, slide in enumerate(slides):
            raw_b64 = slide.get("baked_webp_base64") or slide.get("background_base64") or ""
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            raw_bytes = base64.b64decode(raw_b64) if raw_b64 else b"RIFF\x1a\x00\x00\x00WEBPVP8 "
            encoded_bytes, final_ext, _ = encode_image_bytes(raw_bytes, output_format=pil_fmt, quality=quality)
            slide_filename = _build_slide_filename(slide.get("seo_filename"), product.sku, idx, final_ext)

            media_res = await connector.upload_media_with_seo(
                file_bytes=encoded_bytes,
                filename_slug=slide_filename,
                alt_text=slide.get("alt_text") or f"{product.title} - {idx + 1}",
                title_text=slide.get("title_text") or product.title,
                output_format=pil_fmt,
            )
            if "attachment_id" in media_res:
                uploaded_media_ids.append(media_res["attachment_id"])

        push_res = await connector.push_product_package(
            external_product_id=ext_id,
            media_ids=uploaded_media_ids,
            isolated_rich_html=protected["description"],
            seo_meta=seo_meta,
            short_description_html=protected["short_description"],
            dry_run=False,
        )
        if TaskStatus(task.status) == TaskStatus.UPLOADING:
            task.status = TaskStateMachine.transition(TaskStatus.UPLOADING, TaskStatus.SUCCESS).value
            await db.commit()
        return {
            "preview_only": False,
            "task_id": task.id,
            "fsm_status": task.status,
            "fsm_status_label": translate_status(task.status, lang=payload.lang),
            "output_format": pil_fmt.lower(),
            "uploaded_media_ids": uploaded_media_ids,
            "cms_response": push_res,
        }
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error_trace = str(exc)
        await db.commit()
        if isinstance(exc, PlatformBaseError):
            raise
        raise CMSConnectorError(f"WooCommerce publication failed: {exc}") from exc
