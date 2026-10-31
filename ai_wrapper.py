import time
import io
import logging
from typing import Optional
import requests
from PIL import Image

from server_backend.exceptions import AppNetworkError, InvalidImageError

logger = logging.getLogger("ai_wrapper")

class AIWrapper:
    """
    Изолированный программный адаптер-мост для реализации режима HYBRID.
    Перенаправляет тяжелую обработку на бесплатные внешние API-ноды Hugging Face / Fal / Prodia.
    Полностью инкапсулирует логику сетевой стабильности и политики повторов (Retry Policy).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        # Настройки политики повторных попыток по Единому Регламенту
        self.retry_delays = [2, 4, 8]  # Экспоненциальные паузы в секундах
        self.timeout = 25.0            # Максимальное время ожидания ответа API

    def remove_background_remote(self, image_bytes: bytes) -> bytes:
        """
        Удаление фона через внешнее API (Пример интеграции с Hugging Face Inference API / bria-rmbg).
        Инкапсулирует отказоустойчивость: при ошибках выбрасывает AppNetworkError.
        """
        url = "https://huggingface.co"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info("[🌐 AI_WRAPPER]: Отправка запроса на удаление фона через внешнее API...")
        return self._execute_request_with_retry(url, headers, image_bytes)

    def upscale_image_remote(self, image_bytes: bytes) -> bytes:
        """
        Увеличение резкости/апскейл через внешнее API.
        Заменяет локальный OpenCV инференс в режиме HYBRID для разгрузки CPU.
        """
        url = "https://huggingface.co"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info("[🌐 AI_WRAPPER]: Отправка запроса на ИИ-апскейл резкости через внешнее API...")
        return self._execute_request_with_retry(url, headers, image_bytes)

    def _execute_request_with_retry(self, url: str, headers: dict, data: bytes) -> bytes:
        """
        Внутренний исполнитель HTTP-запросов с поддержкой экспоненциального Retry Policy
        и жесткой изоляцией сетевых сбоев.
        """
        attempt = 0
        total_attempts = len(self.retry_delays) + 1

        while True:
            attempt += 1
            try:
                response = requests.post(
                    url, 
                    headers=headers, 
                    data=data, 
                    timeout=self.timeout
                )

                # Обработка специфического поведения Hugging Face (модель может прогреваться)
                if response.status_code == 503 and "estimated_time" in response.text:
                    estimated_time = response.json().get("estimated_time", 5.0)
                    logger.warning(f"[⏳ API МОДЕЛЬ ЗАГРУЖАЕТСЯ]: Ожидание {estimated_time} сек...")
                    time.sleep(min(estimated_time, 10.0))
                    continue

                # Если сервер вернул ошибку авторизации или лимитов (4xx/5xx)
                if response.status_code != 200:
                    raise requests.exceptions.HTTPError(
                        f"API вернул статус-код {response.status_code}. Ответ: {response.text[:100]}"
                    )

                # Проверка валидности полученного бинарного контента
                result_bytes = response.content
                if not result_bytes or len(result_bytes) < 100:
                    raise InvalidImageError("Внешнее API вернуло пустой или поврежденный буфер данных.")

                # Валидируем, что это действительно графический файл, не ломая поток
                try:
                    with Image.open(io.BytesIO(result_bytes)) as img:
                        img.verify()
                except Exception:
                    raise InvalidImageError("Контент от внешнего API не прошел валидацию структуры изображения.")

                return result_bytes

            # ИСПРАВЛЕНО: HTTPError теперь вызывается строго через модуль requests.exceptions
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as net_err:
                logger.warning(f"[⚠️ СЕТЕВОЙ СБОЙ] Попытка {attempt}/{total_attempts} не удалась: {str(net_err)}")
                
                # Если попытки исчерпаны — оборачиваем в системное AppNetworkError по регламенту
                if attempt > len(self.retry_delays):
                    raise AppNetworkError(
                        f"Не удалось выполнить ИИ-операцию через внешнее API после {total_attempts} попыток. "
                        f"Причина первоисточника: {str(net_err)}"
                    )

                # Экспоненциальное засыпание воркера перед повторным запросом
                sleep_time = self.retry_delays[attempt - 1]
                logger.info(f"[💤 RETRY POLICY]: Ожидание {sleep_time} сек перед повторной отправкой...")
                time.sleep(sleep_time)

            except Exception as e:
                # Повторно перехватываем внутренние ошибки валидации (например, InvalidImageError)
                if isinstance(e, InvalidImageError):
                    raise e
                
                # Все остальные непредвиденные сбои привязываем к сетевым на последней попытке
                if attempt > len(self.retry_delays):
                    raise AppNetworkError(f"Критическая ошибка шлюза вычислений: {str(e)}")
                time.sleep(1)
