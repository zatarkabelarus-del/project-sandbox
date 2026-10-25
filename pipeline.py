import os
import io
from PIL import Image

# 1. ИМПОРТЫ
from server_backend.image_processing.background import BackgroundManager
from server_backend.image_processing.effects import EffectsManager
from server_backend.image_processing.canvas import CanvasManager
from server_backend.image_processing.overlays import apply_watermark
from server_backend.image_processing.ai_upscale import AIUpscaler  
from server_backend.core.validator import ImageValidator  # Подключаем валидатор

class ImageProcessingPipeline:
    def __init__(self):
        # 2. ИНИЦИАЛИЗАЦИЯ (модели загружаются в ОЗУ один раз при старте бэкенда)
        self.bg_manager = BackgroundManager()
        self.effects_manager = EffectsManager()
        self.canvas_manager = CanvasManager()
        self.upscaler = AIUpscaler()  

    def process_stream(
        self,
        image_bytes: bytes,
        shadow: bool = True,
        scale: float = 0.85,
        watermark_pos: str = "bottom_right"
    ) -> bytes:
        """
        Высокоскоростной сквозной конвейер. Принимает бинарные байты,
        обрабатывает в ОЗУ и возвращает оптимизированные бинарные байты.
        """
        try:
            # Читаем входящий поток байт в объект PIL
            raw_image = Image.open(io.BytesIO(image_bytes))
            
            # --- ШАГ 0: Умная валидация пропорций маркетплейса (1:1) ---
            valid_image = ImageValidator.enforce_aspect_ratio(raw_image, target_ratio="1:1")

            # --- АДАПТАЦИЯ ДЛЯ КОРРЕКТНОЙ СЕГМЕНТАЦИИ ---
            # Сохраняем валидированное изображение в байтовый буфер, который ведет себя как файл
            img_byte_arr = io.BytesIO()
            valid_image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0) # Сбрасываем указатель в начало "файла"

            # --- ШАГ 1: Локальное ИИ-удаление фона ---
            print("[Конвейер -> 1/4] ИИ-сегментация фона и вычисление маски товара...")
            
            # Передаем буфер в bg_manager. Если ваш bg_manager строго требует строку-путь, 
            # мы временно сохраняем во временный файл temp.png в корне, чтобы не ломать архитектуру:
            temp_raw_path = "temp_gateway.png"
            valid_image.save(temp_raw_path, format="PNG")
            
            # Передаем путь ИИ-модулю удаления фона
            img_no_bg = self.bg_manager.remove_background_and_crop(temp_raw_path)

            # Чистим временный файл шлюза с диска, чтобы не оставлять мусор
            if os.path.exists(temp_raw_path):
                os.remove(temp_raw_path)

            # --- ИИ Резкость (Апскейл) ---
            print("[Конвейер -> ИИ Резкость] Повышение четкости контуров и текстуры объекта...")
            img_no_bg = self.upscaler.upscale_image(img_no_bg)

            # --- ШАГ 2: Применение эффектов мягких теней ---
            print("[Конвейер -> 2/4] Расчет геометрии эффектов...")
            img_with_effects = self.effects_manager.create_drop_shadow(
                img_no_bg, 
                enabled=shadow, 
                offset_x=12, 
                offset_y=18, 
                blur_radius=15, 
                shadow_opacity=0.35
            )

            # --- ШАГ 3: Интеграция в финальный холст ---
            print("[Конвейер -> 3/4] Пропорциональное вписывание в финальный холст...")
            scale_percent = scale * 100.0
            final_canvas = self.canvas_manager.resize_and_place_on_canvas(
                source_image=img_with_effects,
                canvas_width=1000,
                canvas_height=1000,
                unit="px",
                scale_percent=scale_percent,
                background_color=(255, 255, 255)
            )

            # --- ШАГ 4: Наложение водяного знака интернет-магазина ---
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            logo_path = os.path.join(base_dir, "logo.png")
            
            if os.path.exists(logo_path) and watermark_pos != "none":
                print(f"[Конвейер -> 4/4] Наложение финального водяного знака ({watermark_pos})...")
                final_canvas = apply_watermark(
                    base_image=final_canvas,
                    watermark_path=logo_path,
                    position=watermark_pos,
                    padding=30,
                    opacity=0.55
                )

            # --- ЭКСПОРТ В ПОТОК БАЙТ ---
            output_buffer = io.BytesIO()
            final_card = final_canvas.convert("RGB")
            final_card.save(output_buffer, format="JPEG", quality=95)
            
            return output_buffer.getvalue()

        except Exception as e:
            print(f"[🔴 СБОЙ В ПОТОКОВОМ КОНВЕЙЕРЕ]: {e}")
            raise e

    def process_item(
        self,
        source_path: str,
        output_path: str,
        logo_path: str = None,
        canvas_size: tuple = (1000, 1000),
        scale_percent: float = 85.0,
        bg_color: tuple = (255, 255, 255),
        shadow_enabled: bool = False,
        blur_radius: int = 0
    ) -> bool:
        """
        Чистый сквозной конвейер обработки БЕЗ создания временных файлов на диске.
        Вся передача данных идет строго через оперативную память (PIL объекты).
        """
        try:
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"Файл не найден: {source_path}")

            print(f"\n[🔄 PIPELINE] Потоковая обработка: {os.path.basename(source_path)}")

            # --- ШАГ 1: Локальное ИИ-удаление фона ---
            print("[Конвейер -> 1/4] ИИ-сегментация фона и вычисление маски товара...")
            img_no_bg = self.bg_manager.remove_background_and_crop(source_path)

            # --- ВНЕДРЕНИЕ АПСКЕЙЛЕРА (Сразу после удаления фона) ---
            print("[Конвейер -> ИИ Резкость] Повышение четкости контуров и текстуры объекта...")
            img_no_bg = self.upscaler.upscale_image(img_no_bg)

            # --- ШАГ 2: Применение независимых эффектов ---
            print("[Конвейер -> 2/4] Фильтрация краев и расчет геометрии эффектов...")
            if blur_radius > 0:
                img_no_bg = self.effects_manager.apply_blur_edges(img_no_bg, radius=blur_radius)
            
            # Применяем тень (если enabled=False, менеджер вернет чистый img_no_bg)
            img_with_effects = self.effects_manager.create_drop_shadow(
                img_no_bg, 
                enabled=shadow_enabled, 
                offset_x=12, 
                offset_y=18, 
                blur_radius=15, 
                shadow_opacity=0.35
            )

            # --- ШАГ 3: Интеграция в холст (Прямой прием из памяти) ---
            print("[Конвейер -> 3/4] Пропорциональное вписывание в финальный холст...")
            final_canvas = self.canvas_manager.resize_and_place_on_canvas(
                source_image=img_with_effects,
                canvas_width=canvas_size[0],
                canvas_height=canvas_size[1],
                unit="px",
                scale_percent=scale_percent,
                background_color=bg_color
            )

            # --- ШАГ 4: Наложение водяного знака ---
            if logo_path and os.path.exists(logo_path):
                print("[Конвейер -> 4/4] Наложение финального водяного знака (Alpha Blending)...")
                final_canvas = apply_watermark(
                    base_image=final_canvas,
                    watermark_path=logo_path,
                    position="bottom_right",
                    padding=30,
                    opacity=0.55
                )
            else:
                print("[Конвейер -> 4/4] Пропуск наложения водяного знака.")

            # --- ОКОНЧАТЕЛЬНАЯ СБОРКА И ЭКСПОРТ ---
            final_card = final_canvas.convert("RGB")
            
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                final_card.save(output_path, "JPEG", quality=95)
            else:
                final_card.save(output_path, "PNG")

            print(f"[🟢 PIPELINE УСПЕХ] Готовая карточка сгенерирована: {os.path.basename(output_path)}")
            return True

        except Exception as e:
            print(f"[🔴 СБОЙ В КОНВЕЙЕРЕ]: {e}")
            return False
