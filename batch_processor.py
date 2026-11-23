import asyncio
import traceback
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid
from database.models import BatchJob, GenerationTask, PilotTemplate, Product
from database.session import AsyncSessionLocal

from agents.critic import CriticAgent
from agents.layout_engine import LayoutEngine
from agents.marketer import MarketerAgent
from agents.scene_designer import SceneDesigner
from agents.vision_analyst import VisionAnalyst
from core.budget_limiter import BudgetLimiter
from core.exceptions import AIProviderNetworkError, CMSConnectorError
from core.fsm import TaskStateMachine, TaskStatus
from database.models import GenerationTask, PilotTemplate, Product


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

            bbox = task.vision_brief.get("detected_bbox", [0.22, 0.20, 0.56, 0.60])
            lock_bg = bool((approved_schema or {}).get("lock_backgrounds", True))
            lock_plate = bool((approved_schema or {}).get("lock_plate_style", True))
            pilot_slides = (approved_schema or {}).get("slides", []) if isinstance((approved_schema or {}).get("slides"), list) else []
            slides_list = task.marketing_funnel.get("slides", [])
            scene_idea = str((task.vision_brief or {}).get("visual_scene_idea") or "").strip() or "modern clean commercial interior"
            shared_hero_bg: dict[str, Any] | None = None

            if clean_first_slide and slides_list:
                first_slide_obj = slides_list.__getitem__(0)
                ref_first = next((ps for ps in pilot_slides if int(ps.get("slideIndex", 0)) == 1), pilot_slides.__getitem__(0) if pilot_slides else None)
                locked_first_url = str((ref_first or {}).get("backgroundUrl") or "").strip() if (approved_schema and lock_bg) else ""
                if locked_first_url:
                    shared_hero_bg = {
                        "background_layer_url": locked_first_url,
                        "reused_from_pilot": True,
                        "image_model": image_model or "nanobanana-flash",
                    }
                else:
                    role_hint = str(first_slide_obj.get("role") or "").strip()
                    hero_hint = f"{scene_idea} ({role_hint})" if role_hint else scene_idea
                    shared_hero_bg = await self._run_with_retry(
                        lambda: self.scene_agent.generate_background(
                            product_id=product.sku,
                            style_archetype=style_code,
                            mode=scene_mode,
                            bbox=bbox,
                            image_model=image_model,
                            environment_hint=hero_hint,
                        ),
                        retry_delays=retry_delays,
                    )

            async def _build_single_slide(slide: dict[str, Any]) -> dict[str, Any]:
                s_idx = int(slide.get("slide_index", 1))
                if clean_first_slide and s_idx in (1, 2) and shared_hero_bg is not None:
                    bg_res = dict(shared_hero_bg)
                else:
                    ref_slide = next((ps for ps in pilot_slides if int(ps.get("slideIndex", 0)) == s_idx), pilot_slides.__getitem__(0) if pilot_slides else None)
                    locked_bg_url = str((ref_slide or {}).get("backgroundUrl") or "").strip() if (approved_schema and lock_bg) else ""

                    if locked_bg_url:
                        bg_res = {
                            "background_layer_url": locked_bg_url,
                            "reused_from_pilot": True,
                            "image_model": image_model or "nanobanana-flash",
                        }
                    else:
                        role_hint = str(slide.get("role") or "").strip()
                        slide_scene_hint = f"{scene_idea} (slide {s_idx}: {role_hint})" if role_hint else scene_idea
                        bg_res = await self._run_with_retry(
                            lambda: self.scene_agent.generate_background(
                                product_id=product.sku,
                                style_archetype=style_code,
                                mode=scene_mode,
                                bbox=bbox,
                                image_model=image_model,
                                environment_hint=slide_scene_hint,
                            ),
                            retry_delays=retry_delays,
                        )
                layout = self.layout_engine.compose_layers(
                    slide_data=slide,
                    background_data=bg_res,
                    product_bbox=bbox,
                    style_code=style_code,
                    approved_master_schema=approved_schema,
                    lock_plate_style=lock_plate,
                    clean_first_slide=clean_first_slide,
                )
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

