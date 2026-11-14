from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store(Base):
    """Подключенный интернет-магазин или площадка (CMS-независимая модель)."""
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), default="woocommerce", nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, default="", nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    products: Mapped[list["Product"]] = relationship(back_populates="store", cascade="all, delete-orphan")


class VisualStyle(Base):
    """Паспорт визуального стиля из библиотеки стилей (JSON-паспорт + превью)."""
    __tablename__ = "visual_styles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    archetype: Mapped[str] = mapped_column(String(64), nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    style_passport: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    preview_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Product(Base):
    """Универсальная карточка товара, загруженная из CMS, Excel/CSV или напрямую."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id", ondelete="SET NULL"), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_short_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    embedded_blocks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reviews_summary: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_channel: Mapped[str] = mapped_column(String(32), default="direct_upload", nullable=False)
    packaging_status: Mapped[str] = mapped_column(String(32), default="not_packaged", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    store: Mapped[Optional["Store"]] = relationship(back_populates="products")
    tasks: Mapped[list["GenerationTask"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class PilotTemplate(Base):
    """Утвержденный пользователем Мастер-шаблон после этапа ПИЛОТ для запуска СЕРИИ."""
    __tablename__ = "pilot_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    pilot_product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    style_code: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_layout_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scene_mode: Mapped[str] = mapped_column(String(32), default="studio", nullable=False)
    enable_vision: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GenerationTask(Base):
    """Задача конечного автомата (FSM) с чекпоинтами каждого шага и слайда."""
    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    pilot_template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pilot_templates.id", ondelete="SET NULL"), nullable=True)
    is_pilot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    current_step: Mapped[str] = mapped_column(String(64), default="init", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    vision_brief: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    marketing_funnel: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    slides_payload: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rich_content_html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    seo_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    product: Mapped["Product"] = relationship(back_populates="tasks")


class AuditLog(Base):
    """Журнал аудита операций, расхода бюджета и выгрузок в CMS."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
