import os
from PIL import Image

# 1. ИМПОРТЫ (в самом верху файла)
from server_backend.image_processing.background import BackgroundManager
from server_backend.image_processing.effects import EffectsManager
from server_backend.image_processing.canvas import CanvasManager
from server_backend.image_processing.overlays import apply_watermark
from server_backend.image_processing.ai_upscale import AIUpscaler  # Новый ИИ-апскейлер

class ImageProcessingPipeline:
    def __init__(self):
        # 2. ИНИЦИАЛИЗАЦИЯ (модели загружаются в ОЗУ один раз при старте бэкенда)
        self.bg_manager = BackgroundManager()
        self.effects_manager = EffectsManager()
        self.canvas_manager = CanvasManager()
        self.upscaler = AIUpscaler()  # Добавили инициализацию апскейлера

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
