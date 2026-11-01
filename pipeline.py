import os
import io
import gc
from PIL import Image

# Импорты внутренних модулей графического ядра бэкенда
from server_backend.image_processing.background import BackgroundManager
from server_backend.image_processing.effects import EffectsManager
from server_backend.image_processing.canvas import CanvasManager
from server_backend.image_processing.overlays import apply_watermark
from server_backend.image_processing.ai_upscale import AIUpscaler  
from server_backend.image_processing.metadata import MetadataManager  
from server_backend.core.validator import ImageValidator  
from server_backend.exceptions import InvalidImageError

class ImageProcessingPipeline:
    def __init__(self, mode: str = "HYBRID", api_key: str = None):
        self.mode = mode
        self.bg_manager = BackgroundManager(mode=mode, api_key=api_key)
        self.effects_manager = EffectsManager()
        self.canvas_manager = CanvasManager()
        self.upscaler = AIUpscaler(mode=mode, api_key=api_key)
        self.metadata_manager = MetadataManager()  

    def process_stream(
        self,
        image_bytes: bytes,
        shadow: bool = True,
        scale: float = 0.85,
        watermark_pos: str = "bottom_right",
        meta_ctx: dict = None,          
        style_config: dict = None       
    ) -> bytes:
        """
        Высокоскоростной сквозной конвейер. Работает строго в ОЗУ.
        Защищен от утечек памяти под ограничения жесткого регламента ПК 1.
        """
        raw_image = None
        valid_image = None
        img_no_bg = None
        img_with_effects = None
        final_canvas = None
        
        try:
            try:
                raw_image = Image.open(io.BytesIO(image_bytes))
                raw_image.load()
            except Exception:
                raise InvalidImageError("Передан поврежденный или невалидный графический файл")
            
            # --- ШАГ 0: Умная валидация пропорций (1:1) ---
            valid_image = ImageValidator.enforce_aspect_ratio(raw_image, target_ratio="1:1")

            # --- ШАГ 1: Адаптивное ИИ-удаление фона (In-Memory) ---
            print(f"[Конвейер -> {self.mode}] ИИ-сегментация фона товара в ОЗУ...")
            img_no_bg = self.bg_manager.process_image_object(valid_image)

            # --- ИИ Резкость (Апскейл OpenCV) ---
            print("[Конвейер -> ИИ Резкость] Повышение четкости контуров...")
            img_no_bg = self.upscaler.upscale_image(img_no_bg)

            # --- ШАГ 2: Применение эффектов мягких теней ---
            print("[Конвейер -> 2/4] Расчет геометрии эффектов...")
            shadow_opts = style_config.get("shadow", {}) if style_config else {}
            img_with_effects = self.effects_manager.create_drop_shadow(
                img_no_bg, 
                enabled=shadow, 
                offset_x=shadow_opts.get("offset_x", 12), 
                offset_y=shadow_opts.get("offset_y", 18), 
                blur_radius=shadow_opts.get("blur_radius", 15), 
                shadow_opacity=shadow_opts.get("shadow_opacity", 0.35)
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

            # --- ШАГ 3.5: СЕРВЕРНЫЙ SMART LAYOUT РЕНДЕРИНГ ИНФОГРАФИКИ ---
            if meta_ctx and "slides_infographics" in meta_ctx:
                print("[Конвейер -> Smart Layout] Динамическая сборка плашек инфографики...")
                flat_lines = []
                for slide in meta_ctx["slides_infographics"]:
                    if isinstance(slide, list):
                        flat_lines.extend(slide)
                    else:
                        flat_lines.append(slide)

                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                font_path = os.path.join(base_dir, "desktop_client", "locales", "Arial.ttf")
                
                final_canvas = self.canvas_manager.render_infographics(
                    canvas=final_canvas,
                    lines=flat_lines,
                    font_path=font_path if os.path.exists(font_path) else None
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

            # --- ЭКСПОРТ И ИНВАРИАНТНАЯ SEO ГЕНЕРАЦИЯ EXIF ---
            output_buffer = io.BytesIO()
            final_card = final_canvas.convert("RGB")
            final_card.save(output_buffer, format="JPEG", quality=95)
            raw_bytes = output_buffer.getvalue()

            if meta_ctx and "title" in meta_ctx:
                print("[Конвейер -> SEO] Внедрение нише-независимых EXIF-тегов...")
                temp_path = os.path.join(base_dir, "storage", f"temp_exif_{os.getpid()}.jpg")
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                
                with open(temp_path, "wb") as f:
                    f.write(raw_bytes)
                
                site_context = meta_ctx.get("site_context", "zatarka.by")
                seo_tags = self.metadata_manager.generate_seo_tags(meta_ctx["title"], site_context=site_context)
                self.metadata_manager.write_exif_tags(temp_path, seo_tags)
                
                with open(temp_path, "rb") as f:
                    raw_bytes = f.read()
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            return raw_bytes

        except Exception as e:
            print(f"[🔴 СБОЙ В ПОТОКОВОМ КОНВЕЙЕРЕ]: {e}")
            raise e
            
        finally:
            for obj in [raw_image, valid_image, img_no_bg, img_with_effects, final_canvas]:
                if obj:
                    try:
                        obj.close()
                    except:
                        pass
                    del obj
            gc.collect()

    def process_item(self, source_path: str, output_path: str, logo_path: str = None, canvas_size: tuple = (1000, 1000), scale_percent: float = 85.0, bg_color: tuple = (255, 255, 255), shadow_enabled: bool = False, blur_radius: int = 0) -> bool:
        """Локальный сквозной файловый конвейер."""
        raw_image_loc = None
        img_no_bg = None
        img_with_effects = None
        final_canvas = None
        try:
            if not os.path.exists(source_path): return False
            raw_image_loc = Image.open(source_path)
            img_no_bg = self.bg_manager.process_image_object(raw_image_loc)
            img_no_bg = self.upscaler.upscale_image(img_no_bg)
            if blur_radius > 0:
                img_no_bg = self.effects_manager.apply_blur_edges(img_no_bg, radius=blur_radius)
            img_with_effects = self.effects_manager.create_drop_shadow(img_no_bg, enabled=shadow_enabled, offset_x=12, offset_y=18, blur_radius=15, shadow_opacity=0.35)
            final_canvas = self.canvas_manager.resize_and_place_on_canvas(source_image=img_with_effects, canvas_width=canvas_size, canvas_height=canvas_size, unit="px", scale_percent=scale_percent, background_color=bg_color)
            if logo_path and os.path.exists(logo_path):
                final_canvas = apply_watermark(base_image=final_canvas, watermark_path=logo_path, position="bottom_right", padding=30, opacity=0.55)
            final_card = final_canvas.convert("RGB")
            final_card.save(output_path, "JPEG", quality=95)
            return True
        except: return False
        finally:
            for obj in [raw_image_loc, img_no_bg, img_with_effects, final_canvas]:
                if obj: del obj
            gc.collect()
