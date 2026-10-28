import requests
import os
from PySide6.QtCore import QThread, Signal

class ImageWorker(QThread):
    """
    Изолированный рабочий поток для пакетной отправки изображений на бэкенд FastAPI.
    Не позволяет графическому интерфейсу PySide6 зависать во время сетевых запросов.
    """
    # Сигналы для безопасной передачи состояния из потока в GUI
    progress_updated = Signal(int, str)  # (текущий_индекс_файла, имя_файла)
    file_success = Signal(str, bytes)    # (имя_файла, бинарный_контент_ответа_png)
    file_failed = Signal(str, str)       # (имя_файла, текст_ошибки)
    finished_all = Signal()              # Сигнал полного завершения всей пачки

    def __init__(self, server_url: str, file_paths: list, params: dict):
        super().__init__()
        self.server_url = server_url.rstrip('/')
        self.file_paths = file_paths
        self.params = params  # Словарь с ключами: shadow, scale, watermark_pos

    def run(self):
        endpoint = f"{self.server_url}/api/v1/process-image"
        
        for index, path in enumerate(self.file_paths):
            if not os.path.exists(path):
                self.file_failed.emit(os.path.basename(path), "Файл не найден на диске")
                continue

            filename = os.path.basename(path)
            # Уведомляем интерфейс, какой файл по счету пошел в обработку
            self.progress_updated.emit(index + 1, filename)

            try:
                with open(path, 'rb') as f:
                    files = {'file': (filename, f, 'image/jpeg')}
                    # Преобразуем параметры в строковый формат для multipart/form-data
                    data = {
                        'shadow': str(self.params.get('shadow', True)).lower(),
                        'scale': str(self.params.get('scale', 0.85)),
                        'watermark_pos': str(self.params.get('watermark_pos', 'bottom_right'))
                    }
                    
                    response = requests.post(endpoint, files=files, data=data, timeout=60)
                    
                    if response.status_code == 200:
                        # Возвращаем имя файла и массив байт готового PNG
                        self.file_success.emit(filename, response.content)
                    else:
                        error_msg = f"Ошибка сервера (Код {response.status_code})"
                        self.file_failed.emit(filename, error_msg)
                        
            except requests.exceptions.RequestException as e:
                self.file_failed.emit(filename, f"Сетевой сбой: {str(e)}")

        self.finished_all.emit()


class ServerAPI:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self._worker = None  # Ссылка на текущий запущенный поток

    def check_connection(self):
        try:
            response = requests.get(self.base_url + "/api/health", timeout=5)
            return response.json().get("status") == "ok"
        except:
            return False

    def fetch_products(self):
        """Запрос к серверу для получения списка товаров"""
        try:
            print("[Клиент] Отправляю запрос на сервер за товарами...")
            response = requests.get(self.base_url + "/api/products", timeout=15)
            print(f"[Клиент] Код ответа от сервера: {response.status_code}")
            
            if response.status_code == 200:
                return response.json().get("products", [])
            return []
        except Exception as e:
            print(f"[Клиент] Ошибка при отправке запроса: {e}")
            return []

    def process_batch_images(self, file_paths: list, params: dict, 
                             on_progress, on_success, on_failed, on_finish) -> bool:
        """
        Конфигурирует и запускает асинхронный поток пакетной ИИ-обработки фото.
        Возвращает False, если поток уже занят работой.
        """
        if self._worker and self._worker.isRunning():
            return False  # Защита от повторного клика во время работы
            
        self._worker = ImageWorker(self.base_url, file_paths, params)
        
        # Напрямую связываем сигналы потока с колбэками из главного окна GUI
        self._worker.progress_updated.connect(on_progress)
        self._worker.file_success.connect(on_success)
        self._worker.file_failed.connect(on_failed)
        self._worker.finished_all.connect(on_finish)
        
        self._worker.start()
        return True
