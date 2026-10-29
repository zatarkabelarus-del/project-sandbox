import os
import io
import gc
from PIL import Image

# 1. ИМПОРТЫ
from server_backend.image_processing.background import BackgroundManager
from server_backend.image_processing.effects import EffectsManager
from server_backend.image_processing.canvas import CanvasManager
from server_backend.image_processing.overlays import apply_watermark
from server_backend.image_processing.ai_upscale import AIUpscaler  
from server_backend.core.validator import ImageValidator  
from server_backend.exceptions import InvalidImageError

class ImageProcessingPipeline:
    def __init__(self, mode: str = "HYBRID", api_key: str = None):
        # Модели инициализируются с оглядкой на архитектурный режим
        self.mode = mode
        self.bg_manager = BackgroundManager(mode=mode, api_key=api_key)
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
        Высокоскоростной сквозной конвейер. Работает строго в ОЗУ.
        Внедрен оборонительный контроль утечек памяти под ограничения ПК 1.
        """
        raw_image = None
        valid_image = None
        img_no_bg = None
        img_with_effects = None
        final_canvas = None
        
        try:
            # Читаем поток байт
            try:
                raw_image = Image.open(io.BytesIO(image_bytes))
                raw_image.load()
            except Exception:
                raise InvalidImageError("Передан поврежденный или невалидный графический файл")
            
            # --- ШАГ 0: Умная валидация пропорций маркетплейса (1:1) ---
            valid_image = ImageValidator.enforce_aspect_ratio(raw_image, target_ratio="1:1")

            # --- ШАГ 1: Адаптивное ИИ-удаление фона (Полный In-Memory) ---
            print(f"[Конвейер -> {self.mode}] ИИ-сегментация фона товара в ОЗУ...")
            img_no_bg = self.bg_manager.process_image_object(valid_image)

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

            # --- ШАГ 4: Наложение водяного знака интернет-магазина zatarka ---
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
            
        finally:
            # Жесткий деструктуринг объектов по Единому Регламенту для ПК 1
            for obj in [raw_image, valid_image, img_no_bg, img_with_effects, final_canvas]:
                if obj:
                    try:
                        obj.close()
                    except:
                        pass
                    del obj
            gc.collect()

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
        Локальный сквозной файловый конвейер (сохранен в исходном виде 
        с добавлением безопасного менеджмента контекстов PIL).
        """
        raw_image_loc = None
        img_no_bg = None
        img_with_effects = None
        final_canvas = None
        
        try:
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"Файл не найден: {source_path}")

            print(f"\n[🔄 PIPELINE] Локальная обработка файла: {os.path.basename(source_path)}")
            raw_image_loc = Image.open(source_path)

            # --- ШАГ 1: ИИ-удаление фона ---
            print("[Конвейер -> 1/4] ИИ-сегментация фона...")
            img_no_bg = self.bg_manager.process_image_object(raw_image_loc)

            # --- АПСКЕЙЛЕР ---
            print("[Конвейер -> ИИ Резкость] Повышение четкости контуров...")
            img_no_bg = self.upscaler.upscale_image(img_no_bg)

            # --- ШАГ 2: Применение независимых эффектов ---
            print("[Конвейер -> 2/4] Фильтрация краев...")
            if blur_radius > 0:
                img_no_bg = self.effects_manager.apply_blur_edges(img_no_bg, radius=blur_radius)
            
            img_with_effects = self.effects_manager.create_drop_shadow(
                img_no_bg, 
                enabled=shadow_enabled, 
                offset_x=12, 
                offset_y=18, 
                blur_radius=15, 
                shadow_opacity=0.35
            )

            # --- ШАГ 3: Интеграция в холст ---
            print("[Конвейер -> 3/4] Вписывание в холст...")
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
                print("[Конвейер -> 4/4] Наложение финального водяного знака...")
                final_canvas = apply_watermark(
                    base_image=final_canvas,
                    watermark_path=logo_path,
                    position="bottom_right",
                    padding=30,
                    opacity=0.55
                )

            # Экспорт результата
            final_card = final_canvas.convert("RGB")
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                final_card.save(output_path, "JPEG", quality=95)
            else:
                final_card.save(output_path, "PNG")

            print(f"[🟢 PIPELINE УСПЕХ] Карточка сгенерирована: {os.path.basename(output_path)}")
            return True

        except Exception as e:
            print(f"[🔴 СБОЙ В КОНВЕЙЕРЕ]: {e}")
            return False
            
        finally:
            for obj in [raw_image_loc, img_no_bg, img_with_effects, final_canvas]:
                if obj:
                    try:
                        obj.close()
                    except:
                        pass
                    del obj
            gc.collect()
