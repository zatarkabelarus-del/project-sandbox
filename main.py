import base64
from contextlib import asynccontextmanager
from typing import Any
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.providers.factory import get_ai_provider
from agents.style_factory import StyleFactory
from connectors.excel_csv_importer import ExcelCsvImporter
from connectors.woocommerce import WooCommerceConnector
from core.budget_limiter import BudgetLimiter
from core.config import get_settings
from core.exceptions import CMSConnectorError, PlatformBaseError
from core.fsm import TaskStateMachine, TaskStatus
from core.i18n import load_locale, translate_error, translate_status
from core.security import SecretVault
from database.models import GenerationTask, PilotTemplate, Product, Store
from database.session import get_db, init_db
from workers.batch_processor import BatchProcessor


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    app.state.settings = settings
    app.state.vault = SecretVault(settings.master_key)
    app.state.budget = BudgetLimiter(daily_limit_usd=settings.daily_budget_limit_usd)
    app.state.ai_provider = get_ai_provider()
    app.state.batch_processor = BatchProcessor(budget_limiter=app.state.budget)
    yield


settings = get_settings()
app = FastAPI(title="AI PicChanger+SEO Core API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PlatformBaseError)
async def platform_exception_handler(request: Request, exc: PlatformBaseError) -> JSONResponse:
    lang = request.query_params.get("lang", "ru")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.code,
            "message": exc.message,
            "localized_message": translate_error(exc.code, lang=lang),
            "details": exc.details,
        },
    )


class SecretMaskRequest(BaseModel):
    secret_value: str = Field(..., min_length=1)


class FSMTransitionRequest(BaseModel):
    current_status: TaskStatus
    target_status: TaskStatus
    lang: str = "ru"


class PilotPreviewRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    image_url: str = "https://example.com"
    category: str = "general"
    style_archetype: str = "minimal_light"
    generation_mode: str = "studio"
    enable_vision: bool = True
    slides_count: int = Field(default=5, ge=1, le=10)
    lang: str = "ru"


class PilotApproveRequest(BaseModel):
    name: str = Field(..., min_length=1)
    pilot_product_id: int
    style_code: str = "minimal_light"
    approved_layout_schema: dict[str, Any]
    scene_mode: str = "studio"
    enable_vision: bool = True


class BatchRunRequest(BaseModel):
    pilot_template_id: int
    product_ids: list[int] = Field(..., min_length=1)
    lang: str = "ru"


class WooCommercePublishRequest(BaseModel):
    task_id: int
    store_id: int | None = None
    store_url: str | None = None
    consumer_key: str | None = None
    consumer_secret: str | None = None
    bridge_token: str | None = None
    external_product_id: str | None = None
    preview_only: bool = True
    lang: str = "ru"


@app.get("/api/health")
async def health_check(request: Request, lang: str = Query(default="ru")) -> dict[str, Any]:
    app_settings = request.app.state.settings
    budget: BudgetLimiter = request.app.state.budget
    locale_data = load_locale(lang)
    mode_value = app_settings.app_mode.value
    return {
        "status": "ok",
        "app_mode": mode_value,
        "app_mode_label": locale_data.get("modes", {}).get(mode_value, mode_value),
        "provider": request.app.state.ai_provider.provider_name,
        "budget": {
            "daily_limit_usd": budget.daily_limit_usd,
            "spent_today_usd": budget.spent_today_usd,
            "remaining_usd": budget.remaining_usd,
        },
    }


@app.get("/api/locales/{lang}")
async def get_locale_dictionary(lang: str) -> dict[str, Any]:
    return {"lang": lang.lower(), "dictionary": load_locale(lang)}


@app.post("/api/security/mask-secret")
async def encrypt_and_mask_secret(request: Request, payload: SecretMaskRequest) -> dict[str, Any]:
    vault: SecretVault = request.app.state.vault
    encrypted = vault.encrypt_secret(payload.secret_value)
    return {"stored_encrypted": True, "encrypted_length": len(encrypted), "masked_preview": vault.mask_secret(payload.secret_value)}


@app.post("/api/fsm/transition")
async def transition_task_status(payload: FSMTransitionRequest) -> dict[str, Any]:
    next_status = TaskStateMachine.transition(payload.current_status, payload.target_status)
    return {
        "previous_status": payload.current_status.value,
        "current_status": next_status.value,
        "localized_label": translate_status(next_status.value, lang=payload.lang),
    }


@app.get("/api/styles")
async def list_visual_styles() -> dict[str, Any]:
    factory = StyleFactory()
    return {"styles": factory.list_available_styles()}
@app.post("/api/catalog/import-table")
async def import_catalog_table(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    raw_bytes = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".xlsx"):
        report = ExcelCsvImporter.parse_xlsx_bytes(raw_bytes)
    else:
        report = ExcelCsvImporter.parse_csv_bytes(raw_bytes)

    created_ids: list[int] = []
    for item in report["items"]:
        prod = Product(
            sku=item["sku"],
            title=item["title"],
            category_name=item["category_name"],
            price=item["price"],
            attributes=item["attributes"],
            raw_description=item["raw_description"],
            source_images=item["source_images"],
            source_channel="excel_csv",
        )
        db.add(prod)
        await db.flush()
        created_ids.append(prod.id)
    await db.commit()

    return {
        "total_rows": report["total_rows"],
        "valid_count": report["valid_count"],
        "error_count": report["error_count"],
        "created_product_ids": created_ids,
        "errors": report["errors"],
    }


@app.post("/api/pilot/preview")
async def run_pilot_preview(request: Request, payload: PilotPreviewRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    prod = Product(
        sku=payload.product_id,
        title=payload.title,
        category_name=payload.category,
        source_images=[payload.image_url] if payload.image_url else [],
        source_channel="direct_upload",
    )
    db.add(prod)
    await db.flush()

    task = GenerationTask(product_id=prod.id, is_pilot=True, status=TaskStatus.PENDING.value)
    db.add(task)
    await db.commit()

    processor: BatchProcessor = request.app.state.batch_processor
    done_task = await processor.process_single_task(
        db=db,
        task_id=task.id,
        style_code=payload.style_archetype,
        scene_mode=payload.generation_mode,
        enable_vision=payload.enable_vision,
        slides_count=payload.slides_count,
        lang=payload.lang,
    )
    return {
        "db_product_id": prod.id,
        "task_id": done_task.id,
        "product_id": payload.product_id,
        "fsm_status": done_task.status,
        "fsm_status_label": translate_status(done_task.status, lang=payload.lang),
        "vision": done_task.vision_brief,
        "marketing_and_seo": done_task.marketing_funnel,
        "slides": done_task.slides_payload,
        "rich_content_html": done_task.rich_content_html,
        "seo": done_task.seo_payload,
    }


@app.post("/api/pilot/approve")
async def approve_pilot_template(payload: PilotApproveRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    tpl = PilotTemplate(
        name=payload.name,
        pilot_product_id=payload.pilot_product_id,
        style_code=payload.style_code,
        approved_layout_schema=payload.approved_layout_schema,
        scene_mode=payload.scene_mode,
        enable_vision=payload.enable_vision,
        is_approved=True,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return {"pilot_template_id": tpl.id, "is_approved": tpl.is_approved, "style_code": tpl.style_code}


@app.post("/api/batch/run")
async def run_batch_series(request: Request, payload: BatchRunRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    tpl = (await db.execute(select(PilotTemplate).where(PilotTemplate.id == payload.pilot_template_id))).scalar_one_or_none()
    if not tpl or not tpl.is_approved:
        raise HTTPException(status_code=400, detail="Approved PilotTemplate is required before batch execution")

    task_ids: list[int] = []
    for pid in payload.product_ids:
        t = GenerationTask(product_id=pid, pilot_template_id=tpl.id, is_pilot=False, status=TaskStatus.PENDING.value)
        db.add(t)
        await db.flush()
        task_ids.append(t.id)
    await db.commit()

    processor: BatchProcessor = request.app.state.batch_processor
    summary = await processor.process_batch(db=db, task_ids=task_ids, pilot_template_id=tpl.id, lang=payload.lang)
    return {"pilot_template_id": tpl.id, "batch_summary": summary}


@app.post("/api/publish/woocommerce")
async def publish_to_woocommerce(
    request: Request,
    payload: WooCommercePublishRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = (await db.execute(select(GenerationTask).where(GenerationTask.id == payload.task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"GenerationTask {payload.task_id} not found")

    product = (await db.execute(select(Product).where(Product.id == task.product_id))).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {task.product_id} not found")

    vault: SecretVault = request.app.state.vault
    store_url = payload.store_url or ""
    c_key = payload.consumer_key or ""
    c_secret = payload.consumer_secret or ""

    if payload.store_id:
        store = (await db.execute(select(Store).where(Store.id == payload.store_id))).scalar_one_or_none()
        if not store:
            raise HTTPException(status_code=404, detail=f"Store {payload.store_id} not found")
        store_url = store_url or store.base_url
        if not c_key and store.encrypted_api_key:
            c_key = vault.decrypt_secret(store.encrypted_api_key)
        if not c_secret and store.encrypted_api_secret:
            c_secret = vault.decrypt_secret(store.encrypted_api_secret)

    ext_id = payload.external_product_id or product.external_id or str(product.id)
    slides: list[dict[str, Any]] = task.slides_payload or []
    seo_meta: dict[str, Any] = task.seo_payload or {}
    rich_html: str = task.rich_content_html or ""

    if payload.preview_only:
        prepared_media = [
            {
                "slide_index": idx + 1,
                "filename_slug": slide.get("seo_filename") or f"{product.sku}-slide-{idx + 1}.webp",
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
            "media_plan": prepared_media,
            "isolated_rich_html": rich_html,
            "seo_meta": seo_meta,
        }

    if not store_url or not c_key or not c_secret:
        raise CMSConnectorError("WooCommerce store credentials are required for live publication")

    current_status = TaskStatus(task.status)
    if current_status == TaskStatus.PILOT_REVIEW:
        current_status = TaskStateMachine.transition(current_status, TaskStatus.READY_TO_PUBLISH)
    if current_status == TaskStatus.READY_TO_PUBLISH:
        task.status = TaskStateMachine.transition(current_status, TaskStatus.UPLOADING).value
        await db.commit()

    connector = WooCommerceConnector(
        base_url=store_url,
        consumer_key=c_key,
        consumer_secret=c_secret,
        bridge_token=payload.bridge_token,
    )

    try:
        uploaded_media_ids: list[int | str] = []
        for idx, slide in enumerate(slides):
            raw_b64 = slide.get("baked_webp_base64") or slide.get("background_base64") or ""
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(raw_b64) if raw_b64 else b"RIFF\x1a\x00\x00\x00WEBPVP8 "
            slug = slide.get("seo_filename") or f"{product.sku}-slide-{idx + 1}.webp"
            alt_text = slide.get("alt_text") or f"{product.title} - {idx + 1}"
            title_text = slide.get("title_text") or product.title

            media_res = await connector.upload_media_with_seo(
                file_bytes=img_bytes,
                filename_slug=slug,
                alt_text=alt_text,
                title_text=title_text,
            )
            if "attachment_id" in media_res:
                uploaded_media_ids.append(media_res["attachment_id"])

        push_res = await connector.push_product_package(
            external_product_id=ext_id,
            media_ids=uploaded_media_ids,
            isolated_rich_html=rich_html,
            seo_meta=seo_meta,
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
            "uploaded_media_ids": uploaded_media_ids,
            "cms_response": push_res,
        }
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error_message = str(exc)
        await db.commit()
        if isinstance(exc, PlatformBaseError):
            raise
        raise CMSConnectorError(f"WooCommerce publication failed: {exc}") from exc
