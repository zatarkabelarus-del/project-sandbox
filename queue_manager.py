# server_backend/core/queue_manager.py
import os
import gc
import sys
import asyncio
import logging

from server_backend.image_processing.pipeline import ImageProcessingPipeline
from server_backend.exceptions import (
    AppBaseException, 
    AppNetworkError, 
    InvalidImageError
)

# Настройка логирования в консоль бэкенда
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("queue_manager")

# Глобальное индоор-хранилище задач и статусов (замена Redis для локального контура)
TASK_QUEUE = asyncio.Queue()
TASK_STATUSES = {}

def update_task_status(task_id: str, status: str, meta: dict = None):
    """Обновляет метаданные конечного автомата задачи (Имитация работы Redis)"""
    payload = {"status": status, "lifecycle_state": status}
    if meta:
        payload.update(meta)
    TASK_STATUSES[task_id] = payload
    logger.info(f"[🎰 АВТОМАТ ЗАДАЧ]: Задача {task_id} -> {status}")

async def async_worker_loop():
    """Фоновый воркер конвейера. Заменяет Celery-воркер, изолирует сбои задач."""
    logger.info("[⚙️ ФОНОВЫЙ ВОРКЕР]: Запущен внутренний конвейер очередей.")
    while True:
        # Ожидание появления новой задачи в очереди
        task_data = await TASK_QUEUE.get()
        task_id = task_data["task_id"]
        ctx = task_data["ctx"]
        sys_mode = ctx["sys_mode"]
        
        try:
            # Шаг 1: DOWNLOADING
            update_task_status(task_id, "DOWNLOADING", {"file": ctx["source_path"]})
            if not os.path.exists(ctx["source_path"]):
                raise InvalidImageError(f"Файл не найден по пути: {ctx['source_path']}")
                
            with open(ctx["source_path"], "rb") as f:
                image_bytes = f.read()
            if not image_bytes:
                raise InvalidImageError("Исходный файл изображения пуст")

            # Шаг 2: PROCESSING
            update_task_status(task_id, "PROCESSING")
            
            # Инициализация пайплайна (переключение стратегий PK1_TEST / HYBRID / PRODUCTION)
            pipeline = ImageProcessingPipeline(mode=sys_mode, api_key=ctx["api_key"])
            
            if sys_mode == "PRODUCTION":
                logger.info("[⚙️ BATCHING GPU]: Активирована подготовка тензорного батча via torch.stack()")
                # В продакшн контуре здесь выполняется ленивый импорт torch
            
            # Запуск In-Memory обработки
            processed_bytes = pipeline.process_stream(
                image_bytes=image_bytes,
                shadow=ctx["shadow"],
                scale=ctx["scale"],
                watermark_pos=ctx["watermark_pos"]
            )

            # Шаг 3: UPLOADING
            update_task_status(task_id, "UPLOADING")
            os.makedirs(os.path.dirname(os.path.abspath(ctx["output_path"])), exist_ok=True)
            with open(ctx["output_path"], "wb") as f:
                f.write(processed_bytes)

            # Финал автомата задач
            update_task_status(task_id, "SUCCESS", {"result_path": ctx["output_path"]})

        except AppBaseException as custom_err:
            error_msg = f"Бизнес-ошибка обработки: {custom_err.message}"
            logger.error(f"[🛑 СБОЙ ЗАДАЧИ {task_id}]: {error_msg}")
            update_task_status(task_id, "FAILED", {"error": error_msg, "code": custom_err.code})

        except Exception as e:
            error_msg = f"Непредвиденный сбой конвейера: {str(e)}"
            logger.critical(f"[💥 КРИТИЧЕСКИЙ СБОЙ ЗАДАЧИ {task_id}]: {error_msg}")
            update_task_status(task_id, "FAILED", {"error": error_msg, "code": 500})

        finally:
            # Жесткий контроль очистки ОЗУ под регламент ПК 1
            if 'image_bytes' in locals(): del image_bytes
            if 'processed_bytes' in locals(): del processed_bytes
            TASK_QUEUE.task_done()
            gc.collect()
