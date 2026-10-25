import os
import urllib.request
import cv2
import numpy as np
from PIL import Image

class AIUpscaler:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_dir = os.path.join(self.base_dir, "models")
        os.makedirs(self.model_dir, exist_ok=True)
        
        # Используем модель FSRCNN (быстрая, идеально восстанавливает жесткие края предметов)
        self.model_path = os.path.join(self.model_dir, "FSRCNN_x2.pb")
        self.model_url = "https://githubusercontent.com"
        
        # Инициализируем нейросетевой движок OpenCV
        self.sr = cv2.dnn_superres.DnnSuperResImpl_create()
        self._ensure_model_loaded()

    def _ensure_model_loaded(self):
        """Автоматическая загрузка весов модели ИИ с защитой от сбоев сети"""
        # Если файла нет или он весит меньше 1 КБ (битый)
        if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000:
            print("[-] ИИ-модель апскейла не найдена или повреждена. Попытка загрузки весов FSRCNN (около 40 КБ)...")
            try:
                url = "https://githubusercontent.com"
                urllib.request.urlretrieve(url, self.model_path)
                print("[+] Модель успешно загружена!")
            except Exception as e:
                print(f"[⚠️ СЕТЕВОЙ СБОЙ] Не удалось скачать модель ИИ (нет интернета): {e}")
                print("[⚠️ ПРЕДУПРЕЖДЕНИЕ] Апскейлер временно деактивирован до появления сети.")
                return # Выходим, не ломая запуск сервера

        # Безопасная инициализация движка OpenCV только при реальном наличии файла
        if os.path.exists(self.model_path) and os.path.getsize(self.model_path) > 1000:
            try:
                self.sr.readModel(self.model_path)
                self.sr.setModel("fsrcnn", 2)
                print("[+] Движок ИИ-сверхрезкости успешно инициализирован.")
            except Exception as e:
                print(f"[🔴 ОШИБКА ИНИЦИАЛИЗАЦИИ МОДЕЛИ]: {e}")
        else:
            print("[⚠️ ВНИМАНИЕ] Файл модели отсутствует. Сверхрезкость будет временно пропускаться.")

    def upscale_image(self, pil_image: Image.Image) -> Image.Image:
        """
        Принимает PIL-изображение, повышает контурную резкость.
        Если модель не загружена — безопасно возвращает оригинал без сбоев.
        """
        # Защитная проверка: если движок OpenCV не готов, просто возвращаем исходное фото
        try:
            # Проверяем, настроена ли модель внутри OpenCV
            if not os.path.exists(self.model_path) or os.path.getsize(self.model_path) < 1000:
                return pil_image
                
            has_alpha = pil_image.mode == "RGBA"
            np_img = np.array(pil_image)
            
            if has_alpha:
                cv_img = cv2.cvtColor(np_img, cv2.COLOR_RGBA2BGR)
                alpha_channel = np_img[:, :, 3]
            else:
                cv_img = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)

            print("[ИИ Апскейл] Запуск нейросети FSRCNN_x2...")
            upscaled_bgr = self.sr.upsample(cv_img)

            if has_alpha:
                upscaled_alpha = cv2.resize(alpha_channel, (upscaled_bgr.shape[1], upscaled_bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
                result_cv = cv2.merge([upscaled_bgr[:,:,0], upscaled_bgr[:,:,1], upscaled_bgr[:,:,2], upscaled_alpha])
                result_pil = Image.fromarray(cv2.cvtColor(result_cv, cv2.COLOR_BGRA2RGBA))
            else:
                result_cv = cv2.cvtColor(upscaled_bgr, cv2.COLOR_BGR2RGB)
                result_pil = Image.fromarray(result_cv)

            return result_pil
        except Exception as e:
            print(f"[⚠️ СБОЙ ИИ АПСКЕЙЛА]: {e}. Безопасный пропуск шага резкости.")
            return pil_image
