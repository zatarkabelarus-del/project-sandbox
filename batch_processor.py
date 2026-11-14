import asyncio
import traceback
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
                approved_schema = tpl.approved_layout_schema
                style_code = tpl.style_code
                scene_mode = tpl.scene_mode
                enable_vision = tpl.enable_vision

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
                vision_res = await self._run_with_retry(
                    lambda: self.vision_agent.analyze_product(
                        product_id=product.sku,
                        title=product.title,
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
                mkt_res = await self._run_with_retry(
                    lambda: self.marketer_agent.build_funnel_and_seo(
                        product_id=product.sku,
                        title=product.title,
                        attributes={**product.attributes, "category": product.category_name},
                        vision_brief=task.vision_brief,
                        slides_count=slides_count,
                        lang=lang,
                    ),
                    retry_delays=retry_delays,
                )
                self.budget.check_and_consume("marketer", float(mkt_res.get("estimated_cost_usd", 0.0)))
                task.marketing_funnel = mkt_res
                task.rich_content_html = mkt_res.get("rich_content_html", "")
                task.seo_payload = mkt_res.get("seo", {})
                await db.commit()

            # Шаг 3: Генерация фонов + Auto-Layout + Critic (чекпоинт)
            if current == TaskStatus.ANALYZING:
                current = TaskStateMachine.transition(current, TaskStatus.GENERATING_BG)
                task.status = current.value
                task.current_step = "generating_slides"
                await db.commit()

            bbox = task.vision_brief.get("detected_bbox", [0.22, 0.20, 0.56, 0.60])
            composed_slides: list[dict[str, Any]] = []
            for slide in task.marketing_funnel.get("slides", []):
                bg_res = await self._run_with_retry(
                    lambda: self.scene_agent.generate_background(
                        product_id=product.sku,
                        style_archetype=style_code,
                        mode=scene_mode,
                        bbox=bbox,
                    ),
                    retry_delays=retry_delays,
                )
                layout = self.layout_engine.compose_layers(
                    slide_data=slide,
                    background_data=bg_res,
                    product_bbox=bbox,
                    style_code=style_code,
                    approved_master_schema=approved_schema,
                )
                qa_report = await self.critic_agent.validate_slide(
                    product_id=product.sku,
                    slide_index=slide.get("slide_index", 1),
                    layout_schema=layout,
                )
                composed_slides.append({
                    "slide_index": slide.get("slide_index", 1),
                    "role": slide.get("role", ""),
                    "alt_text": slide.get("alt_text", ""),
                    "file_slug": slide.get("file_slug", ""),
                    "layout_schema": layout,
                    "qa_report": qa_report,
                })

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
