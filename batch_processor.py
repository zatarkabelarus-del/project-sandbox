import asyncio
import traceback
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid
from database.models import BatchJob, GenerationTask, PilotTemplate, Product
from database.session import AsyncSessionLocal

import base64
import io
from PIL import Image, ImageFilter, ImageOps

from agents.critic import CriticAgent
from agents.layout_engine import LayoutEngine
from agents.marketer import MarketerAgent
from agents.scene_designer import SceneDesigner
from agents.vision_analyst import VisionAnalyst
from core.budget_limiter import BudgetLimiter
from core.exceptions import AIProviderNetworkError, CMSConnectorError
from core.fsm import TaskStateMachine, TaskStatus
from database.models import GenerationTask, PilotTemplate, Product
from graphics.bg_remover import remove_background_bytes


def _composite_product_onto_saved_bg(bg_data_url: str, product_img_url: str) -> str:
    """Студийный Python-композитинг: накладывает вырезанный товар на чистый фон со светом, рефлексом и 2-слойной тенью."""
    if not bg_data_url.startswith("data:image/") or "," not in bg_data_url:
        return product_img_url
    if not product_img_url.startswith("data:image/") or "," not in product_img_url:
        return bg_data_url
    try:
        bg_bytes = base64.b64decode(bg_data_url.split(",", 1).pop())
        prod_bytes = base64.b64decode(product_img_url.split(",", 1).pop())
        cutout_png_bytes, _, _ = remove_background_bytes(prod_bytes)

        bg_img = ImageOps.exif_transpose(Image.open(io.BytesIO(bg_bytes))).convert("RGBA")
        bw, bh = bg_img.size
        prod_rgba = Image.open(io.BytesIO(cutout_png_bytes)).convert("RGBA")
        alpha_bbox = prod_rgba.getchannel("A").getbbox()
        if alpha_bbox:
            prod_rgba = prod_rgba.crop(alpha_bbox)

        max_w, max_h = int(bw * 0.54), int(bh * 0.56)
        prod_rgba = ImageOps.contain(prod_rgba, (max_w, max_h), method=Image.Resampling.LANCZOS)
        pw, ph = prod_rgba.size
        px = (bw - pw) // 2
        py = max(0, int(bh * 0.50 - ph // 2))

        alpha_ch = prod_rgba.getchannel("A")

        # 1. Мягкая рассеянная студийная тень
        ambient_shadow = Image.new("RGBA", prod_rgba.size, (15, 23, 42, 85))
        ambient_shadow.putalpha(alpha_ch.point(lambda a: int(a * 0.24)))
        ambient_shadow = ambient_shadow.filter(ImageFilter.GaussianBlur(radius=18))
        bg_img.alpha_composite(ambient_shadow, (px, min(bh - ph, py + 14)))

        # 2. Плотная контактная тень у основания предмета
        contact_shadow = Image.new("RGBA", prod_rgba.size, (9, 13, 22, 130))
        contact_shadow.putalpha(alpha_ch.point(lambda a: int(a * 0.34)))
        contact_shadow = contact_shadow.filter(ImageFilter.GaussianBlur(radius=6))
        bg_img.alpha_composite(contact_shadow, (px, min(bh - ph, py + 5)))

        # 3. Деликатный световой рефлекс (Light Wrap) по краю контура в средний тон фона
        bg_avg = bg_img.resize((1, 1), resample=Image.Resampling.BILINEAR).getpixel((0, 0))
        rim_tint = Image.new("RGBA", prod_rgba.size, (bg_avg[0], bg_avg[1], bg_avg[2], 255))
        eroded_alpha = alpha_ch.filter(ImageFilter.MinFilter(3))
        edge_mask = Image.eval(
            Image.composite(Image.new("L", alpha_ch.size, 0), alpha_ch, eroded_alpha),
            lambda v: int(v * 0.22),
        )
        prod_lit = prod_rgba.copy()
        prod_lit.paste(rim_tint, (0, 0), edge_mask)

        bg_img.alpha_composite(prod_lit, (px, py))

        out = io.BytesIO()
        bg_img.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"
    except Exception:
        return product_img_url

class BatchProcessor:
    """
    Оркестратор полного цикла:
    - Пилот (останавливается в статусе PILOT_REVIEW для ручного утверждения);
    - Серия (применяет утвержденный PilotTemplate к группе товаров с изоляцией сбоев).
    """

    RETRY_DELAYS = (2, 4, 8)

    def __init__(self, budget_limiter: BudgetLimiter) -> None:
        self.budget = budget_limiter
        self.vision_agent = VisionAnalyst()
        self.marketer_agent = MarketerAgent()
        self.scene_agent = SceneDesigner()
        self.layout_engine = LayoutEngine()
        self.critic_agent = CriticAgent()

    async def _run_with_retry(self, coro_factory, retry_delays: tuple[int, ...] | None = None) -> Any:
        delays = retry_delays if retry_delays is not None else self.RETRY_DELAYS
        last_exc: Exception | None = None
        for attempt in range(len(delays) + 1):
            try:
                return await coro_factory()
            except (AIProviderNetworkError, CMSConnectorError) as exc:
                last_exc = exc
                if attempt < len(delays):
                    await asyncio.sleep(delays[attempt])
        raise last_exc  # type: ignore[misc]

    async def process_single_task(
        self,
        db: AsyncSession,
        task_id: int,
        style_code: str = "minimal_light",
        scene_mode: str = "studio",
        enable_vision: bool = True,
        slides_count: int = 5,
        image_model: str | None = None,
        avoid_title_duplication: bool = False,
        clean_first_slide: bool = False,
        lang: str = "ru",
        retry_delays: tuple[int, ...] | None = None,
    ) -> GenerationTask:
        stmt = select(GenerationTask).where(GenerationTask.id == task_id)
        task = (await db.execute(stmt)).scalar_one()
        prod_stmt = select(Product).where(Product.id == task.product_id)
        product = (await db.execute(prod_stmt)).scalar_one()

        approved_schema: dict[str, Any] | None = None
        if task.pilot_template_id:
            tpl_stmt = select(PilotTemplate).where(PilotTemplate.id == task.pilot_template_id)
            tpl = (await db.execute(tpl_stmt)).scalar_one_or_none()
            if tpl and tpl.is_approved:
                approved_schema = tpl.approved_layout_schema or {}
                style_code = tpl.style_code
                scene_mode = tpl.scene_mode
                enable_vision = tpl.enable_vision
                if "slides_count" in approved_schema:
                    slides_count = max(1, min(8, int(approved_schema["slides_count"])))
                if approved_schema.get("image_model"):
                    image_model = str(approved_schema["image_model"])
                if "avoid_title_duplication" in approved_schema:
                    avoid_title_duplication = bool(approved_schema["avoid_title_duplication"])
                if "clean_first_slide" in approved_schema:
                    clean_first_slide = bool(approved_schema["clean_first_slide"])

        try:
            current = TaskStatus(task.status)
            if current == TaskStatus.PENDING:
                current = TaskStateMachine.transition(current, TaskStatus.DOWNLOADING)
                task.status = current.value
                task.current_step = "downloading"
                await db.commit()

            if current == TaskStatus.DOWNLOADING:
                current = TaskStateMachine.transition(current, TaskStatus.ANALYZING)
                task.status = current.value
                task.current_step = "vision_analysis"
                await db.commit()

            # Шаг 1: Vision-анализ (чекпоинт)
            if not task.vision_brief:
                img_url = product.source_images if product.source_images else ""
                hint_parts = [p for p in (product.title, product.raw_short_description, product.raw_description) if p and str(p).strip()]
                combined_hint = " | ".join(str(p).strip() for p in hint_parts)
                vision_res = await self._run_with_retry(
                    lambda: self.vision_agent.analyze_product(
                        product_id=product.sku,
                        title=combined_hint,
                        image_url=img_url,
                        enable_vision=enable_vision,
                        lang=lang,
                    ),
                    retry_delays=retry_delays,
                )
                self.budget.check_and_consume("vision", float(vision_res.get("estimated_cost_usd", 0.0)))
                task.vision_brief = vision_res
                await db.commit()

            # Шаг 2: Маркетолог + SEO + Рич-контент (чекпоинт)
            if not task.marketing_funnel:
                detected_name = str((task.vision_brief or {}).get("detected_product_name") or "").strip()
                effective_title = detected_name if detected_name and (
                    not product.title
                    or "модуль управления" in product.title.lower()
                    or product.title.lower().startswith(("img_", "photo_", "dsc", "screenshot"))
                ) else product.title
                enriched_attrs = {
                    **product.attributes,
                    "category": product.category_name,
                }
                if product.raw_short_description:
                    enriched_attrs["short_description"] = product.raw_short_description
                if product.raw_description:
                    enriched_attrs["full_description"] = product.raw_description

                mkt_res = await self._run_with_retry(
                    lambda: self.marketer_agent.build_funnel_and_seo(
                        product_id=product.sku,
                        title=effective_title,
                        attributes=enriched_attrs,
                        vision_brief=task.vision_brief,
                        slides_count=slides_count,
                        avoid_title_duplication=avoid_title_duplication,
                        lang=lang,
                    ),
                    retry_delays=retry_delays,
                )
                self.budget.check_and_consume("marketer", float(mkt_res.get("estimated_cost_usd", 0.0)))
                task.marketing_funnel = mkt_res
                task.rich_content_html = mkt_res.get("rich_content_html", "")
                task.seo_payload = mkt_res.get("seo", {})
                await db.commit()

            # Шаг 3: Параллельная генерация фонов + Auto-Layout + Critic (чекпоинт)
            if current == TaskStatus.ANALYZING:
                current = TaskStateMachine.transition(current, TaskStatus.GENERATING_BG)
                task.status = current.value
                task.current_step = "generating_slides"
                await db.commit()

            bbox = task.vision_brief.get("detected_bbox", [0.26, 0.22, 0.48, 0.54])
            vision_free_zones = task.vision_brief.get("free_zones") or []
            vision_accent = str(task.vision_brief.get("accent_color") or "").strip()
            lock_bg = bool((approved_schema or {}).get("lock_backgrounds", True))
            lock_plate = bool((approved_schema or {}).get("lock_plate_style", True))
            pilot_slides = (approved_schema or {}).get("slides", []) if isinstance((approved_schema or {}).get("slides"), list) else []
            slides_list = task.marketing_funnel.get("slides", [])
            prod_attrs_safe = product.__dict__.get("attributes") or {}
            user_bg_wish = str(prod_attrs_safe.get("background_prompt") or (approved_schema or {}).get("background_prompt") or "").strip()
            vision_scene_idea = str((task.vision_brief or {}).get("visual_scene_idea") or "").strip()
            scene_idea = user_bg_wish or vision_scene_idea or "tailored commercial environment matching the product"
            raw_src_images = product.__dict__.get("source_images")
            source_img_str = (
                str(next(iter(raw_src_images), "") or "")
                if isinstance(raw_src_images, list)
                else str(raw_src_images or "")
            ).strip()
            # Шаг 3.1: Получаем или берём из Пилота ЧИСТЫЙ ПУСТОЙ ФОН (без товара и текста)
            first_ref = next((ps for ps in pilot_slides if int(ps.get("slideIndex", 0)) == 1), pilot_slides.__getitem__(0) if pilot_slides else None)
            locked_pure_bg = str((first_ref or {}).get("pureBackgroundUrl") or (first_ref or {}).get("backgroundUrl") or "").strip() if (approved_schema and lock_bg) else ""

            if locked_pure_bg:
                pure_bg_res = {
                    "background_layer_url": locked_pure_bg,
                    "reused_from_pilot": True,
                    "scene_includes_product": False,
                    "image_model": image_model or "nanobanana-flash",
                }
            else:
                pure_bg_res = await self._run_with_retry(
                    lambda: self.scene_agent.generate_background(
                        product_id=product.sku,
                        style_archetype=style_code,
                        mode=scene_mode,
                        bbox=bbox,
                        image_model=image_model,
                        environment_hint=scene_idea,
                        source_image_url="",
                    ),
                    retry_delays=retry_delays,
                )

            pure_bg_url = str(pure_bg_res.get("background_layer_url") or "")
            has_live_photo = source_img_str.startswith("data:image/") and pure_bg_url.startswith("data:image/")
            # Шаг 3.2: Собираем в Python эталонный кадр «Чистый фон + Вырезанный товар со светом и тенями»
            python_hero_url = _composite_product_onto_saved_bg(pure_bg_url, source_img_str) if has_live_photo else pure_bg_url

            async def _build_single_slide(slide: dict[str, Any]) -> dict[str, Any]:
                s_idx = int(slide.get("slide_index", 1))
                ref_slide = next((ps for ps in pilot_slides if int(ps.get("slideIndex", 0)) == s_idx), first_ref)
                slide_locked_pure = str((ref_slide or {}).get("pureBackgroundUrl") or (ref_slide or {}).get("backgroundUrl") or "").strip() if (approved_schema and lock_bg) else ""

                if clean_first_slide and s_idx == 1:
                    # Слайд #1 без инфографики: отдаём точный Python-кадр без лишнего вызова нейросети
                    bg_res = {
                        "background_layer_url": python_hero_url,
                        "pure_background_url": pure_bg_url,
                        "scene_includes_product": has_live_photo,
                        "image_model": image_model or "nanobanana-flash",
                    }
                elif not has_live_photo and slide_locked_pure:
                    # Режим DEV_MOCK или URL без data:image — переиспользуем фон пилота без вызова scene_agent
                    bg_res = {
                        "background_layer_url": slide_locked_pure,
                        "pure_background_url": slide_locked_pure,
                        "reused_from_pilot": True,
                        "scene_includes_product": False,
                        "image_model": image_model or "nanobanana-flash",
                    }
                elif has_live_photo:
                    # Накладываем ТОЛЬКО дизайнерскую инфографику ИИ поверх неподвижного python_hero_url
                    headline_t = str(slide.get("headline") or "").strip()
                    pills_list = slide.get("pills") if isinstance(slide.get("pills"), list) else []
                    sub_t = str(slide.get("subheadline") or "").strip()
                    bullets = [str(p).strip() for p in pills_list if str(p).strip()] or ([sub_t] if sub_t else [])
                    copy_part = f"Headline in Russian: '{headline_t}'; Badges in Russian: {', '.join(repr(b) for b in bullets[:3])}"
                    bg_res = await self._run_with_retry(
                        lambda: self.scene_agent.generate_background(
                            product_id=product.sku,
                            style_archetype=style_code,
                            mode=scene_mode,
                            bbox=bbox,
                            image_model=image_model,
                            environment_hint=f"[PRESERVE_BG_AND_PRODUCT] {copy_part}",
                            source_image_url=python_hero_url,
                        ),
                        retry_delays=retry_delays,
                    )
                    bg_res["pure_background_url"] = pure_bg_url
                else:
                    bg_res = dict(pure_bg_res)
                    bg_res["pure_background_url"] = pure_bg_url

                is_ai_native_card = bool(bg_res.get("scene_includes_product", False))
                enriched_slide = {
                    **slide,
                    "_free_zones": vision_free_zones,
                    "_accent_color": vision_accent,
                }
                layout = self.layout_engine.compose_layers(
                    slide_data=enriched_slide,
                    background_data=bg_res,
                    product_bbox=bbox,
                    style_code=style_code,
                    approved_master_schema=approved_schema,
                    lock_plate_style=lock_plate,
                    clean_first_slide=(clean_first_slide or is_ai_native_card),
                )
                if is_ai_native_card:
                    layout["layers"] = []
                layout["scene_includes_product"] = is_ai_native_card
                layout["pure_background_url"] = pure_bg_url
                qa_report = await self.critic_agent.validate_slide(
                    product_id=product.sku,
                    slide_index=slide.get("slide_index", 1),
                    layout_schema=layout,
                )
                return {
                    "slide_index": slide.get("slide_index", 1),
                    "role": slide.get("role", ""),
                    "alt_text": slide.get("alt_text", ""),
                    "file_slug": slide.get("file_slug", ""),
                    "layout_schema": layout,
                    "qa_report": qa_report,
                }

            composed_slides = list(await asyncio.gather(*[_build_single_slide(s) for s in slides_list]))
            task.slides_payload = composed_slides

            # Финал: Пилот идет в PILOT_REVIEW, Серия — в READY_TO_PUBLISH
            if task.is_pilot:
                next_st = TaskStateMachine.transition(TaskStatus(task.status), TaskStatus.PILOT_REVIEW)
                product.packaging_status = "pilot"
            else:
                if TaskStatus(task.status) == TaskStatus.GENERATING_BG:
                    mid_st = TaskStateMachine.transition(TaskStatus.GENERATING_BG, TaskStatus.BATCH_PROCESSING)
                    task.status = mid_st.value
                next_st = TaskStateMachine.transition(TaskStatus(task.status), TaskStatus.READY_TO_PUBLISH)
                product.packaging_status = "draft"

            task.status = next_st.value
            task.current_step = "completed"
            await db.commit()
            return task

        except Exception as exc:
            await db.rollback()
            task.status = TaskStatus.FAILED.value
            task.error_trace = traceback.format_exc()
            await db.commit()
            return task

    async def process_batch(
        self,
        db: AsyncSession,
        task_ids: list[int],
        pilot_template_id: int | None = None,
        lang: str = "ru",
        retry_delays: tuple[int, ...] | None = None,
    ) -> dict[str, Any]:
        """Изолированная пакетная обработка: сбой одного товара не останавливает серию."""
        results = {"total": len(task_ids), "succeeded": 0, "failed": 0, "tasks": []}
        for tid in task_ids:
            if pilot_template_id:
                stmt = select(GenerationTask).where(GenerationTask.id == tid)
                t_obj = (await db.execute(stmt)).scalar_one_or_none()
                if t_obj:
                    t_obj.pilot_template_id = pilot_template_id
                    t_obj.is_pilot = False
                    await db.commit()

            processed = await self.process_single_task(
                db=db,
                task_id=tid,
                lang=lang,
                retry_delays=retry_delays,
            )
            if processed.status == TaskStatus.FAILED.value:
                results["failed"] += 1
            else:
                results["succeeded"] += 1
            results["tasks"].append({"task_id": processed.id, "status": processed.status})
        return results

    async def run_batch_job_background(
        self,
        job_id: str,
        task_ids: list[int],
        pilot_template_id: int | None = None,
        lang: str = "ru",
        retry_delays: tuple[int, ...] | None = None,
    ) -> None:
        """Неблокирующий фоновый воркер с персистентным обновлением прогресса в БД."""
        async with AsyncSessionLocal() as db:
            job = (await db.execute(select(BatchJob).where(BatchJob.id == job_id))).scalar_one_or_none()
            if not job:
                return
            job.status = "RUNNING"
            await db.commit()

            for tid in task_ids:
                await db.refresh(job)
                if job.cancel_requested:
                    job.status = "CANCELLED"
                    job.current_sku = None
                    await db.commit()
                    return

                t_obj = (await db.execute(select(GenerationTask).where(GenerationTask.id == tid))).scalar_one_or_none()
                if not t_obj:
                    continue

                if pilot_template_id:
                    t_obj.pilot_template_id = pilot_template_id
                    t_obj.is_pilot = False
                t_obj.batch_id = job_id

                prod_obj = (await db.execute(select(Product).where(Product.id == t_obj.product_id))).scalar_one_or_none()
                job.current_sku = prod_obj.sku if prod_obj else f"TASK-{tid}"
                await db.commit()

                processed = await self.process_single_task(
                    db=db,
                    task_id=tid,
                    lang=lang,
                    retry_delays=retry_delays,
                )
                job.processed_items += 1
                if processed.status == TaskStatus.FAILED.value:
                    job.failed_count += 1
                else:
                    job.succeeded_count += 1
                await db.commit()

            job.status = "COMPLETED"
            job.current_sku = None
            await db.commit()

    @staticmethod
    def serialize_job(job: BatchJob) -> dict[str, Any]:
        percent = round((job.processed_items / job.total_items) * 100, 1) if job.total_items > 0 else 100.0
        return {
            "job_id": job.id,
            "pilot_template_id": job.pilot_template_id,
            "status": job.status,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "succeeded_count": job.succeeded_count,
            "failed_count": job.failed_count,
            "progress_percent": percent,
            "current_sku": job.current_sku,
            "cancel_requested": job.cancel_requested,
            "error_summary": job.error_summary,
        }

