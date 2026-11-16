from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from agents.marketer import MarketerAgent


from connectors.store_service import (
    DEFAULT_STORE_SETTINGS,
    build_woocommerce_connector,
    encrypt_store_credentials,
    serialize_store_public,
    upsert_synced_products,
)
from core.config import AppMode
from core.exceptions import CMSConnectorError
from database.models import Store
from database.session import get_db

router = APIRouter(prefix="/api", tags=["stores-and-seo"])


class StoreUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    platform: str = "woocommerce"
    base_url: str = Field(..., min_length=1)
    consumer_key: str | None = None
    consumer_secret: str | None = None
    bridge_token: str | None = None
    wp_username: str | None = None
    wp_app_password: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class CatalogSyncRequest(BaseModel):
    store_id: int
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)
    mock_items: list[dict[str, Any]] | None = None


class CategorySeoGenerateRequest(BaseModel):
    categories: list[dict[str, Any]] = Field(..., min_length=1)
    lang: str = "ru"


class CategorySeoPublishRequest(BaseModel):
    store_id: int
    external_category_id: str
    seo_text: str
    meta_title: str
    meta_description: str
    preview_only: bool = True


@router.get("/stores")
async def list_stores(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    vault = request.app.state.vault
    rows = (await db.execute(select(Store).order_by(Store.id.asc()))).scalars().all()
    return {"stores": [serialize_store_public(s, vault) for s in rows]}


@router.post("/stores")
async def create_store(request: Request, payload: StoreUpsertRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    vault = request.app.state.vault
    encrypted = encrypt_store_credentials(
        vault,
        {
            "consumer_key": payload.consumer_key,
            "consumer_secret": payload.consumer_secret,
            "bridge_token": payload.bridge_token,
            "wp_username": payload.wp_username,
            "wp_app_password": payload.wp_app_password,
        },
    )
    merged_settings = {**DEFAULT_STORE_SETTINGS, **(payload.settings or {})}
    store = Store(
        name=payload.name.strip(),
        platform=payload.platform.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
        encrypted_credentials=encrypted,
        settings_json=merged_settings,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return {"store": serialize_store_public(store, vault)}


@router.put("/stores/{store_id}")
async def update_store(
    store_id: int, request: Request, payload: StoreUpsertRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    store = (await db.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    vault = request.app.state.vault
    store.name = payload.name.strip()
    store.platform = payload.platform.strip()
    store.base_url = payload.base_url.strip().rstrip("/")
    store.encrypted_credentials = encrypt_store_credentials(
        vault,
        {
            "consumer_key": payload.consumer_key,
            "consumer_secret": payload.consumer_secret,
            "bridge_token": payload.bridge_token,
            "wp_username": payload.wp_username,
            "wp_app_password": payload.wp_app_password,
        },
        existing_store=store,
    )
    store.settings_json = {**DEFAULT_STORE_SETTINGS, **(store.settings_json or {}), **(payload.settings or {})}
    await db.commit()
    await db.refresh(store)
    return {"store": serialize_store_public(store, vault)}


@router.post("/stores/{store_id}/check-connection")
async def check_store_connection(store_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    store = (await db.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    if request.app.state.settings.app_mode == AppMode.DEV_MOCK:
        return {"store_id": store.id, "connected": True, "mode": "DEV_MOCK"}
    connector = build_woocommerce_connector(store, request.app.state.vault)
    ok = await connector.check_connection()
    return {"store_id": store.id, "connected": ok, "mode": request.app.state.settings.app_mode.value}


@router.post("/catalog/sync-woocommerce")
async def sync_woocommerce_catalog(
    request: Request, payload: CatalogSyncRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    store = (await db.execute(select(Store).where(Store.id == payload.store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {payload.store_id} not found")
    connector = build_woocommerce_connector(store, request.app.state.vault)
    if request.app.state.settings.app_mode == AppMode.DEV_MOCK and payload.mock_items is not None:
        normalized = [connector._normalize_product(raw) for raw in payload.mock_items]
    else:
        normalized = await connector.fetch_products(page=payload.page, per_page=payload.per_page)
    synced_ids = await upsert_synced_products(db, store.id, normalized)
    return {"store_id": store.id, "synced_count": len(synced_ids), "product_ids": synced_ids}


@router.get("/seo/categories")
async def get_store_categories(
    request: Request, store_id: int = Query(...), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    store = (await db.execute(select(Store).where(Store.id == store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    if request.app.state.settings.app_mode == AppMode.DEV_MOCK:
        return {
            "store_id": store.id,
            "categories": [
                {"external_id": "101", "name": "Оборудование и комплектующие", "slug": "equipment", "count": 42, "description": ""},
                {"external_id": "102", "name": "Аксессуары и расходники", "slug": "accessories", "count": 19, "description": ""},
            ],
        }
    connector = build_woocommerce_connector(store, request.app.state.vault)
    return {"store_id": store.id, "categories": await connector.fetch_categories()}


@router.post("/seo/categories/generate")
async def generate_categories_seo(request: Request, payload: CategorySeoGenerateRequest) -> dict[str, Any]:
    marketer = MarketerAgent()
    generated: list[dict[str, Any]] = []
    for cat in payload.categories:
        cat_id = str(cat.get("external_id") or "cat-0")
        cat_name = str(cat.get("name") or "Категория")
        funnel = await marketer.build_funnel_and_seo(
            product_id=f"cat-{cat_id}",
            title=cat_name,
            attributes={"items_count": str(cat.get("count", 0))},
            slides_count=1,
            lang=payload.lang,
        )
        seo = funnel.get("seo", {})
        generated.append(
            {
                "external_id": cat_id,
                "name": cat_name,
                "meta_title": seo.get("meta_title") or f"{cat_name} — купить в каталоге",
                "meta_description": seo.get("meta_description") or f"Широкий выбор товаров в категории {cat_name}.",
                "seo_text": funnel.get("rich_content_html") or f"<p>Каталог категории {cat_name}.</p>",
            }
        )
    return {"items": generated}


@router.post("/seo/categories/publish")
async def publish_category_seo(
    request: Request, payload: CategorySeoPublishRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    store = (await db.execute(select(Store).where(Store.id == payload.store_id))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {payload.store_id} not found")
    connector = build_woocommerce_connector(store, request.app.state.vault)
    if not payload.preview_only and not connector.auth[0]:
        raise CMSConnectorError("WooCommerce store credentials are required for live category SEO export")
    res = await connector.push_category_seo(
        external_category_id=payload.external_category_id,
        seo_text=payload.seo_text,
        meta_title=payload.meta_title,
        meta_description=payload.meta_description,
        dry_run=payload.preview_only,
    )
    return {"store_id": store.id, **res}
