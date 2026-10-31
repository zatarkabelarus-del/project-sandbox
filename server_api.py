import requests
import os
import time
from PySide6.QtCore import QThread, Signal

class ImageWorker(QThread):
    """
    Изолированный рабочий поток для асинхронного взаимодействия с FastAPI сервером.
    Реализует быструю регистрацию пакета и последующий поллинг состояний автомата задач.
    """
    progress_updated = Signal(int, str)       # (текущий_индекс_файла, имя_файла)
    task_status_changed = Signal(str, str)    # (имя_файла, системный_статус_автомата)
    file_success = Signal(str, bytes)        # (имя_файла, бинарный_контент)
    file_failed = Signal(str, str)           # (имя_файла, текст_ошибки)
    finished_all = Signal()                  # Сигнал полного завершения всей пачки

    def __init__(self, server_url: str, file_paths: list, params: dict):
        super().__init__()
        self.server_url = server_url.rstrip('/')
        self.file_paths = file_paths
        self.params = params

    def run(self):
        async_endpoint = f"{self.server_url}/api/v1/process-async"
        tasks_map = {}  # Карта соответствия task_id -> filename

        # Шаг 1: Пакетная мгновенная отправка файлов на Multipart-эндпоинт
        for index, path in enumerate(self.file_paths):
            if not os.path.exists(path):
                self.file_failed.emit(os.path.basename(path), "Файл не найден на диске")
                continue

            filename = os.path.basename(path)
            self.progress_updated.emit(index + 1, filename)
            self.task_status_changed.emit(filename, "PENDING")

            try:
                with open(path, 'rb') as f:
                    files = {'file': (filename, f, 'image/jpeg')}
                    data = {
                        'shadow': str(self.params.get('shadow', True)).lower(),
                        'scale': str(self.params.get('scale', 0.85)),
                        'watermark_pos': str(self.params.get('watermark_pos', 'bottom_right'))
                    }
                    
                    # Мгновенная регистрация задачи на бэкенде
                    response = requests.post(async_endpoint, files=files, data=data, timeout=30)
                    
                    if response.status_code == 200:
                        task_id = response.json().get("task_id")
                        if task_id:
                            tasks_map[task_id] = filename
                        else:
                            self.file_failed.emit(filename, "Сервер не вернул ID задачи")
                    else:
                        self.file_failed.emit(filename, f"Ошибка сервера ({response.status_code})")
                        
            except requests.exceptions.RequestException as e:
                self.file_failed.emit(filename, f"Сетевой сбой при отправке: {str(e)}")

        # Шаг 2: Мониторинг Конечного Автомата задач (Поллинг)
        active_tasks = list(tasks_map.keys())
        
        while active_tasks and not self.isInterruptionRequested():
            for task_id in list(active_tasks):
                status_url = f"{self.server_url}/api/v1/tasks/{task_id}"
                try:
                    res = requests.get(status_url, timeout=5)
                    if res.status_code == 200:
                        task_info = res.json()
                        status = task_info.get("status", "PENDING")
                        filename = tasks_map[task_id]
                        
                        # Эмитим изменение системного статуса для обновления UI
                        self.task_status_changed.emit(filename, status)
                        
                        if status == "SUCCESS":
                            # Скачиваем готовый результат обработки с SSD бэкенда
                            result_url = f"{self.server_url}/api/v1/results/{task_id}"
                            file_res = requests.get(result_url, timeout=15)
                            if file_res.status_code == 200:
                                self.file_success.emit(filename, file_res.content)
                            else:
                                self.file_failed.emit(filename, f"Ошибка загрузки результата")
                            active_tasks.remove(task_id)
                            
                        elif status == "FAILED":
                            error_log = task_info.get("error", "Неизвестная ошибка ИИ-ядра")
                            self.file_failed.emit(filename, error_log)
                            active_tasks.remove(task_id)
                except requests.exceptions.RequestException:
                    # При временном разрыве связи на ПК 1 не ломаем поток, ждем следующей итерации
                    pass
            
            # Интервал поллинга для защиты CPU/сети от перегрузки
            time.sleep(1.5)

        self.finished_all.emit()


class ServerAPI:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self._worker = None

    def check_connection(self):
        try:
            response = requests.get(self.base_url + "/api/health", timeout=5)
            return response.json().get("status") == "ok"
        except:
            return False

    def fetch_products(self):
        try:
            response = requests.get(self.base_url + "/api/products", timeout=15)
            if response.status_code == 200:
                return response.json().get("products", [])
            return []
        except Exception:
            return []

    def process_batch_images(self, file_paths: list, params: dict, 
                             on_progress, on_status_change, on_success, on_failed, on_finish) -> bool:
        if self._worker and self._worker.isRunning():
            return False
            
        self._worker = ImageWorker(self.base_url, file_paths, params)
        
        self._worker.progress_updated.connect(on_progress)
        self._worker.task_status_changed.connect(on_status_change)
        self._worker.file_success.connect(on_success)
        self._worker.file_failed.connect(on_failed)
        self._worker.finished_all.connect(on_finish)
        
        self._worker.start()
        return True
