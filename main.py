import asyncio
import base64
import io
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.providers.factory import get_ai_provider
from agents.style_factory import StyleFactory
from connectors.excel_csv_importer import ExcelCsvImporter
from core.budget_limiter import BudgetLimiter
from core.config import get_settings, load_models_catalog
from core.exceptions import PlatformBaseError
from core.fsm import TaskStateMachine, TaskStatus
from core.i18n import load_locale, translate_error, translate_status
from core.security import SecretVault
from core.token_billing import TokenBillingService
from database.models import BatchJob, GenerationTask, PilotTemplate, Product, Store, User, UserAsset, VisualStyle
from database.session import get_db, init_db
from graphics.batch_exporter import BatchZipExporter
from graphics.bg_remover import remove_background_bytes
from routes_auth_billing import get_optional_current_user, router as auth_billing_router
from routes_publish import router as publish_router
from routes_store_seo import router as store_seo_router
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
app = FastAPI(title="AI PicChanger+SEO Core API", version="0.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_billing_router)
app.include_router(store_seo_router)
app.include_router(publish_router)


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
    product_id: str = Field(default="SKU-CUSTOM")
    title: str = Field(default="")
    short_description: str = Field(default="")
    full_description: str = Field(default="")
    image_url: str = ""
    category: str = "general"
    style_archetype: str = "minimal_light"
    generation_mode: str = "studio"
    enable_vision: bool = True
    slides_count: int = Field(default=5, ge=1, le=8)
    image_model: str | None = None
    avoid_title_duplication: bool = False
    clean_first_slide: bool = False
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
    async_mode: bool = False
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
    return {"styles": StyleFactory().list_available_styles()}

@app.get("/api/models/catalog")
async def get_models_catalog() -> dict[str, Any]:
    catalog = load_models_catalog()
    active_models = [m for m in catalog.get("models", []) if m.get("is_active", True)]
    return {
        "default_model": catalog.get("default_model", "nanobanana-flash"),
        "models": active_models,
    }

@app.post("/api/catalog/import-table")
async def import_catalog_table(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    raw_bytes = await file.read()
    report = (
        ExcelCsvImporter.parse_xlsx_bytes(raw_bytes)
        if (file.filename or "").lower().endswith(".xlsx")
        else ExcelCsvImporter.parse_csv_bytes(raw_bytes)
    )
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
async def run_pilot_preview(
    request: Request,
    payload: PilotPreviewRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    active_model = payload.image_model or load_models_catalog().get("default_model", "nanobanana-flash")
    clean_sku = payload.product_id.strip() or f"SKU-{uuid.uuid4().hex[:6].upper()}"
    clean_title = payload.title.strip()
    clean_short = payload.short_description.strip()
    clean_full = payload.full_description.strip()
    log_title = clean_title or "Товар по фото"

    tokens_spent = await TokenBillingService.charge_user(
        db=db,
        user=current_user,
        operation_type="pilot_preview",
        quantity=1,
        description=f"Генерация Пилота ({payload.slides_count} сл., {active_model}): {log_title}",
        image_model=active_model,
        slides_count=payload.slides_count,
    )
    extra_attrs: dict[str, Any] = {}
    if clean_short:
        extra_attrs["short_description"] = clean_short
    if clean_full:
        extra_attrs["full_description"] = clean_full

    prod = Product(
        sku=clean_sku,
        title=clean_title,
        category_name=payload.category,
        attributes=extra_attrs,
        raw_short_description=clean_short,
        raw_description=clean_full,
        source_images=[payload.image_url] if payload.image_url else [],
        source_channel="direct_upload",
    )
    db.add(prod)
    await db.flush()
    task = GenerationTask(product_id=prod.id, is_pilot=True, status=TaskStatus.PENDING.value)
    db.add(task)
    await db.commit()
    done_task = await request.app.state.batch_processor.process_single_task(
        db=db,
        task_id=task.id,
        style_code=payload.style_archetype,
        scene_mode=payload.generation_mode,
        enable_vision=payload.enable_vision,
        slides_count=payload.slides_count,
        image_model=active_model,
        avoid_title_duplication=payload.avoid_title_duplication,
        clean_first_slide=payload.clean_first_slide,
        lang=payload.lang,
    )
    return {
        "db_product_id": prod.id,
        "task_id": done_task.id,
        "product_id": payload.product_id,
        "image_model": active_model,
        "slides_count": payload.slides_count,
        "avoid_title_duplication": payload.avoid_title_duplication,
        "fsm_status": done_task.status,
        "fsm_status_label": translate_status(done_task.status, lang=payload.lang),
        "vision": done_task.vision_brief,
        "marketing_and_seo": done_task.marketing_funnel,
        "slides": done_task.slides_payload,
        "rich_content_html": done_task.rich_content_html,
        "seo": done_task.seo_payload,
        "tokens_spent": tokens_spent,
    }

@app.post("/api/pilot/approve")
async def approve_pilot_template(
    payload: PilotApproveRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    owner_id = current_user.id if current_user else None
    tpl = PilotTemplate(
        owner_user_id=owner_id,
        name=payload.name,
        pilot_product_id=payload.pilot_product_id,
        style_code=payload.style_code,
        approved_layout_schema=payload.approved_layout_schema,
        scene_mode=payload.scene_mode,
        enable_vision=payload.enable_vision,
        is_approved=True,
    )
    db.add(tpl)
    await db.flush()

    seen_urls: set[str] = set()
    first_plate: dict[str, Any] | None = None
    for s in payload.approved_layout_schema.get("slides", []):
        bg_url = str(s.get("backgroundUrl") or "").strip()
        if bg_url and bg_url not in seen_urls:
            seen_urls.add(bg_url)
            db.add(
                UserAsset(
                    owner_user_id=owner_id,
                    category="my_backgrounds",
                    name=f"{payload.name} #{s.get('slideIndex', 1)}",
                    asset_url=bg_url,
                    source_pilot_id=tpl.id,
                )
            )
        layers = s.get("layers")
        if first_plate is None and isinstance(layers, list) and layers:
            first_plate = next(iter(layers))

    if first_plate:
        db.add(
            VisualStyle(
                code=f"plate_{tpl.id}_{uuid.uuid4().hex[:6]}",
                archetype="my_plates",
                name_i18n={"ru": f"Плашка: {payload.name}", "en": f"Plate: {payload.name}"},
                style_passport={
                    "bgColor": first_plate.get("bgColor", "#0F172A"),
                    "textColor": first_plate.get("textColor", "#FFFFFF"),
                    "borderRadius": first_plate.get("borderRadius", 12),
                    "fontSize": first_plate.get("fontSize", 22),
                },
                is_system=False,
            )
        )

    await db.commit()
    await db.refresh(tpl)
    return {"pilot_template_id": tpl.id, "is_approved": tpl.is_approved, "style_code": tpl.style_code}


@app.get("/api/assets/my-backgrounds")
async def list_my_backgrounds(
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(UserAsset).where(UserAsset.category == "my_backgrounds").order_by(UserAsset.id.desc())
    if current_user is not None:
        stmt = stmt.where(UserAsset.owner_user_id == current_user.id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [{"id": r.id, "category": r.category, "name": r.name, "asset_url": r.asset_url, "source_pilot_id": r.source_pilot_id} for r in rows]}


@app.get("/api/styles/my-plates")
async def list_my_plates(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (await db.execute(select(VisualStyle).where(VisualStyle.archetype == "my_plates").order_by(VisualStyle.id.desc()))).scalars().all()
    return {"items": [{"id": r.id, "code": r.code, "archetype": r.archetype, "name": r.name_i18n.get("ru", r.code), "style_passport": r.style_passport} for r in rows]}


@app.post("/api/graphics/remove-bg")
async def remove_product_background(
    file: UploadFile | None = File(default=None),
    image_url: str = Query(default=""),
) -> dict[str, Any]:
    raw_bytes: bytes | None = None
    if file is not None:
        raw_bytes = await file.read()
    elif image_url.startswith("data:image/") and "," in image_url:
        raw_bytes = base64.b64decode(image_url.split(",", 1).pop())
    else:
        buf = io.BytesIO()
        Image.new("RGB", (400, 400), (248, 250, 252)).save(buf, format="PNG")
        raw_bytes = buf.getvalue()

    _, cutout_data_url, engine_used = remove_background_bytes(raw_bytes)
    return {"cutout_data_url": cutout_data_url, "engine": engine_used, "tokens_spent": 0}


@app.post("/api/assets/upload-background")
async def upload_custom_background(
    file: UploadFile = File(...),
    name: str = Query(default=""),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    raw_bytes = await file.read()
    ext = (file.filename or "bg.webp").rsplit(".", 1).pop().lower()
    mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/webp")
    data_url = f"data:{mime};base64,{base64.b64encode(raw_bytes).decode('ascii')}"
    asset_name = name.strip() or (file.filename or "Пользовательский фон")
    asset = UserAsset(
        owner_user_id=current_user.id if current_user else None,
        category="my_backgrounds",
        name=asset_name,
        asset_url=data_url,
        meta_json={"uploaded": True},
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return {"id": asset.id, "category": asset.category, "name": asset.name, "asset_url": asset.asset_url}
@app.post("/api/batch/run")
async def run_batch_series(
    request: Request,
    payload: BatchRunRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tpl = (await db.execute(select(PilotTemplate).where(PilotTemplate.id == payload.pilot_template_id))).scalar_one_or_none()
    if not tpl or not tpl.is_approved:
        raise HTTPException(status_code=400, detail="Approved PilotTemplate is required before batch execution")

    master_schema = tpl.approved_layout_schema or {}
    tpl_model = str(master_schema.get("image_model") or "") or None
    tpl_slides = int(master_schema.get("slides_count", 5)) if "slides_count" in master_schema else None

    tokens_spent = await TokenBillingService.charge_user(
        db=db,
        user=current_user,
        operation_type="batch_slide",
        quantity=len(payload.product_ids),
        description=f"Пакетная серия ({len(payload.product_ids)} товаров)",
        image_model=tpl_model,
        slides_count=tpl_slides,
    )

    job_id = f"batch-{uuid.uuid4().hex[:12]}"
    job = BatchJob(
        id=job_id,
        owner_user_id=current_user.id if current_user else None,
        pilot_template_id=tpl.id,
        status="QUEUED",
        total_items=len(payload.product_ids),
    )
    db.add(job)

    task_ids: list[int] = []
    for pid in payload.product_ids:
        t = GenerationTask(
            batch_id=job_id,
            product_id=pid,
            pilot_template_id=tpl.id,
            is_pilot=False,
            status=TaskStatus.PENDING.value,
        )
        db.add(t)
        await db.flush()
        task_ids.append(t.id)
    await db.commit()

    processor: BatchProcessor = request.app.state.batch_processor
    if payload.async_mode:
        asyncio.create_task(
            processor.run_batch_job_background(
                job_id=job_id,
                task_ids=task_ids,
                pilot_template_id=tpl.id,
                lang=payload.lang,
            )
        )
        return {
            "job_id": job_id,
            "status": "QUEUED",
            "total_items": len(task_ids),
            "pilot_template_id": tpl.id,
            "tokens_spent": tokens_spent,
        }

    summary = await processor.process_batch(db=db, task_ids=task_ids, pilot_template_id=tpl.id, lang=payload.lang)
    job.status = "COMPLETED"
    job.processed_items = summary["total"]
    job.succeeded_count = summary["succeeded"]
    job.failed_count = summary["failed"]
    await db.commit()
    return {"job_id": job_id, "pilot_template_id": tpl.id, "batch_summary": summary, "tokens_spent": tokens_spent}


@app.get("/api/batch/status/{job_id}")
async def get_batch_job_status(job_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = (await db.execute(select(BatchJob).where(BatchJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return BatchProcessor.serialize_job(job)


@app.get("/api/batch/active")
async def get_latest_batch_job(
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(BatchJob).order_by(BatchJob.created_at.desc()).limit(1)
    if current_user is not None:
        stmt = select(BatchJob).where(BatchJob.owner_user_id == current_user.id).order_by(BatchJob.created_at.desc()).limit(1)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        return {"job": None}
    return {"job": BatchProcessor.serialize_job(job)}


@app.post("/api/batch/cancel/{job_id}")
async def cancel_batch_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = (await db.execute(select(BatchJob).where(BatchJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    job.cancel_requested = True
    await db.commit()
    return BatchProcessor.serialize_job(job)


class ProductLandingRequest(BaseModel):
    sku: str = "SKU-DEMO"
    title: str
    category: str = ""
    price: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_url: str = ""
    theme: str = "light_studio"
    lang: str = "ru"


@app.post("/api/landing/generate")
async def generate_product_landing(
    payload: ProductLandingRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tokens_spent = await TokenBillingService.charge_user(
        db=db,
        user=current_user,
        operation_type="landing_generate",
        quantity=1,
        description=f"Генерация мини-лендинга: {payload.title}",
    )
    await db.commit()

    marketer = app.state.batch_processor.marketer_agent
    funnel = await marketer.build_funnel_and_seo(
        product_id=payload.sku,
        title=payload.title,
        attributes=payload.attributes,
        lang=payload.lang,
    )

    slides = funnel.get("slides", [])
    hero_sub = slides[1].get("subheadline", "") if len(slides) > 1 else funnel.get("usp_summary", "")

    benefits = [
        {"title": s.get("headline", payload.title), "desc": s.get("subheadline", "")}
        for s in slides[1:4]
    ] or [{"title": payload.title, "desc": funnel.get("usp_summary", "")}]

    specs = [{"key": str(k), "value": str(v)} for k, v in payload.attributes.items()]
    if payload.price is not None:
        specs.insert(0, {"key": "Цена" if payload.lang == "ru" else "Price", "value": f"{payload.price}"})

    scenarios = [
        f"Основное применение: {payload.category or 'ежедневная эксплуатация'}" if payload.lang == "ru" else f"Primary use: {payload.category or 'daily operation'}",
        "Быстрая интеграция и стабильная работа под нагрузкой" if payload.lang == "ru" else "Quick setup and reliable performance under load",
    ]
    faq = [
        {
            "q": f"Подходит ли {payload.title} для регулярного использования?" if payload.lang == "ru" else f"Is {payload.title} suitable for regular use?",
            "a": "Да, модель рассчитана на длительный ресурс и проходит контроль качества перед отгрузкой." if payload.lang == "ru" else "Yes, designed for long service life and verified before dispatch.",
        },
        {
            "q": "Какая комплектация и гарантия?" if payload.lang == "ru" else "What is included and what is the warranty?",
            "a": "Поставляется в заводской упаковке с официальной гарантией." if payload.lang == "ru" else "Supplied in factory packaging with official warranty.",
        },
    ]

    bg_main = "#0f172a" if payload.theme == "dark_premium" else ("#eff6ff" if payload.theme == "marketplace_accent" else "#f8fafc")
    fg_main = "#f8fafc" if payload.theme == "dark_premium" else "#0f172a"
    benefits_html = "".join(f"<div style='padding:12px;border:1px solid #cbd5e1;border-radius:10px;'><strong>{b['title']}</strong><p style='margin:6px 0 0;font-size:13px;'>{b['desc']}</p></div>" for b in benefits)
    specs_html = "".join(f"<tr><td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;'><strong>{sp['key']}</strong></td><td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;'>{sp['value']}</td></tr>" for sp in specs)
    faq_html = "".join(f"<div style='margin-top:8px;'><strong>{f['q']}</strong><p style='margin:4px 0 0;font-size:13px;'>{f['a']}</p></div>" for f in faq)
    isolated_html = (
        f"<div class='ai-product-landing' style='font-family:sans-serif;background:{bg_main};color:{fg_main};padding:20px;border-radius:14px;max-width:920px;margin:0 auto;'>"
        f"<h2 style='margin:0 0 8px;font-size:22px;'>{payload.title}</h2>"
        f"<p style='margin:0 0 16px;font-size:14px;opacity:0.85;'>{hero_sub}</p>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px;'>{benefits_html}</div>"
        f"<table style='width:100%;border-collapse:collapse;margin-bottom:16px;font-size:13px;'>{specs_html}</table>"
        f"<div>{faq_html}</div></div>"
    )
    return {
        "hero": {"headline": payload.title, "subheadline": hero_sub, "image_url": payload.image_url},
        "benefits": benefits,
        "specs": specs,
        "scenarios": scenarios,
        "faq": faq,
        "isolated_html": isolated_html,
        "tokens_spent": tokens_spent,
    }
class ManualProductRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    category: str = "general"
    price: float | None = None
    raw_short_description: str = ""
    raw_description: str = ""
    image_data_url: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class ZipExportRequest(BaseModel):
    product_ids: list[int] = Field(default_factory=list)
    output_format: str = "webp"
    output_quality: int = Field(default=90, ge=40, le=100)


@app.post("/api/products/manual")
async def create_manual_product(
    payload: ManualProductRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    prod = Product(
        sku=payload.sku.strip(),
        title=payload.title.strip(),
        category_name=payload.category.strip() or "general",
        price=payload.price,
        attributes=payload.attributes,
        raw_short_description=payload.raw_short_description.strip(),
        raw_description=payload.raw_description.strip(),
        source_images=[payload.image_data_url] if payload.image_data_url.strip() else [],
        source_channel="direct_upload",
    )
    db.add(prod)
    await db.commit()
    await db.refresh(prod)
    return {
        "id": prod.id,
        "sku": prod.sku,
        "title": prod.title,
        "category": prod.category_name,
        "source_channel": prod.source_channel,
    }


@app.post("/api/export/zip-package")
async def export_zip_package(
    payload: ZipExportRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    stmt = select(Product).order_by(Product.id.asc())
    if payload.product_ids:
        stmt = stmt.where(Product.id.in_(payload.product_ids))
    if current_user is not None:
        owned_store_ids = (
            await db.execute(select(Store.id).where(Store.owner_user_id == current_user.id))
        ).scalars().all()
        stmt = stmt.where((Product.store_id.is_(None)) | (Product.store_id.in_(owned_store_ids)))

    products = (await db.execute(stmt)).scalars().all()
    if not products:
        raise HTTPException(status_code=404, detail="No products found for ZIP export")

    records: list[dict[str, Any]] = []
    for prod in products:
        latest_task = (
            await db.execute(
                select(GenerationTask)
                .where(GenerationTask.product_id == prod.id)
                .order_by(GenerationTask.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        records.append(
            {
                "product_id": prod.id,
                "sku": prod.sku,
                "title": prod.title,
                "category": prod.category_name,
                "short_description": prod.raw_short_description,
                "full_description": prod.raw_description,
                "source_images": prod.source_images,
                "slides": latest_task.slides_payload if latest_task else [],
                "seo": latest_task.seo_payload if latest_task else {},
                "marketing": latest_task.marketing_funnel if latest_task else {},
                "rich_content_html": latest_task.rich_content_html if latest_task else "",
            }
        )

    spool = BatchZipExporter.build_zip_spool(
        records=records,
        output_format=payload.output_format,
        quality=payload.output_quality,
    )

    def _iter_spool():
        while True:
            chunk = spool.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        _iter_spool(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="catalog_ready_package.zip"'},
        background=BackgroundTask(spool.close),
    )
