import os
import csv
import uuid
import logging
import gc
from typing import Dict, List, Optional

try:
    import openpyxl
except ImportError:
    openpyxl = None

from server_backend.core.queue_manager import TASK_QUEUE, update_task_status
from server_backend.exceptions import InvalidImageError

logger = logging.getLogger("excel_parser")

class ExcelParser:
    """
    Отказоустойчивый модуль потокового чтения прайс-листов (.xlsx, .xls, .csv).
    Собирает детальную статистику с номерами строк для вывода отчета в интерфейсе.
    """

    def __init__(self):
        pass

    def parse_and_queue(
        self,
        file_path: str,
        id_column_name: str,       
        title_column_name: str,    
        url_column_name: str,      
        features_column_name: str, 
        output_dir: str,           
        sys_mode: str = "HYBRID",
        api_key: Optional[str] = None,
        shadow: bool = True,
        scale: float = 0.85,
        watermark_pos: str = "bottom_right"
    ) -> Dict[str, any]:
        """
        Сканирует таблицу, извлекает данные и ставит задачи в очередь.
        Возвращает детальную статистику по успешным и пропущенным строкам.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл прайс-листа не найден: {file_path}")

        # Исправлено: берем второй элемент кортежа [1] (расширение)
        ext = os.path.splitext(file_path)[1].lower()
        
        # Строго 8 пробелов от начала строки для инициализации словаря
        stats = {
            "successfully_queued": 0,
            "failed_count": 0,
            "failed_rows_details": []
        }

        if ext == ".csv":
            self._parse_csv(file_path, id_column_name, title_column_name, url_column_name, features_column_name, output_dir, sys_mode, api_key, shadow, scale, watermark_pos, stats)
        elif ext in [".xlsx", ".xlsm"]:
            self._parse_xlsx(file_path, id_column_name, title_column_name, url_column_name, features_column_name, output_dir, sys_mode, api_key, shadow, scale, watermark_pos, stats)
        else:
            raise InvalidImageError(f"Неподдерживаемый формат файла прайс-листа: {ext}")

        logger.info(f"[📊 ПАРСЕР ЗАВЕРШЕН]: УСПЕХ: {stats['successfully_queued']}, ОШИБОК: {stats['failed_count']}")
        return stats

    def _parse_csv(self, file_path: str, id_col: str, title_col: str, url_col: str, feat_col: str, output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict):
        """Потоковый парсинг CSV с трекингом физических строк."""
        # Начинаем с 1, так как 1-я строка обычно заголовок
        current_row_index = 1 
        
        with open(file_path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            try:
                sample = f.read(2048)
                f.seek(0)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)
                reader = csv.DictReader(f, dialect=dialect)
            except Exception:
                f.seek(0)
                reader = csv.DictReader(f, delimiter=";")

            for row in reader:
                current_row_index += 1
                try:
                    is_queued = self._process_row_data(
                        row_dict=row, id_col=id_col, title_col=title_col, url_col=url_col,
                        feat_col=feat_col, output_dir=output_dir, mode=mode, key=key,
                        shadow=shadow, scale=scale, w_pos=w_pos, stats=stats
                    )
                    if not is_queued:
                        # Строка без фото — это не сбой, а пропуск. Фиксируем по желанию.
                        pass
                except Exception as row_err:
                    stats["failed_count"] += 1
                    stats["failed_rows_details"].append(f"Строка {current_row_index}: {str(row_err)}")
                    logger.error(f"[⚠️ СБОЙ CSV] Строка {current_row_index}: {str(row_err)}")

    def _parse_xlsx(self, file_path: str, id_col: str, title_col: str, url_col: str, feat_col: str, output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict):
        """Парсинг XLSX в режиме read_only=True с точным трекингом номеров строк."""
        if openpyxl is None:
            raise ImportError("Необходимо установить openpyxl")

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet = wb.active
            
            # Используем enumerate, чтобы знать точный физический номер строки в Excel (начиная с 1)
            for row_idx, row_cells in enumerate(sheet.iter_rows(values_only=True), start=1):
                if row_idx == 1:
                    # Обработка заголовков
                    headers_map = {str(h).strip(): idx for idx, h in enumerate(row_cells) if h is not None}
                    for col_name in [id_col, title_col, url_col, feat_col]:
                        if col_name not in headers_map:
                            raise KeyError(f"Колонка '{col_name}' не найдена в заголовках.")
                    continue

                if not any(row_cells): 
                    continue # Игнорируем пустые строки

                try:
                    row_dict = {}
                    for col_name, idx in headers_map.items():
                        if idx < len(row_cells):
                            row_dict[col_name] = row_cells[idx]

                    self._process_row_data(
                        row_dict=row_dict, id_col=id_col, title_col=title_col, url_col=url_col,
                        feat_col=feat_col, output_dir=output_dir, mode=mode, key=key,
                        shadow=shadow, scale=scale, w_pos=w_pos, stats=stats
                    )
                except Exception as row_err:
                    stats["failed_count"] += 1
                    stats["failed_rows_details"].append(f"Строка {row_idx}: {str(row_err)}")
                    logger.error(f"[⚠️ СБОЙ XLSX] Строка {row_idx}: {str(row_err)}")
                finally:
                    if 'row_dict' in locals(): del row_dict
        finally:
            wb.close()
            del wb
            gc.collect()

    def _process_row_data(self, row_dict: Dict[str, any], id_col: str, title_col: str, url_col: str, feat_col: str, output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict) -> bool:
        """Извлекает данные и пушит в очередь. Возвращает True если задача добавлена."""
        product_id = str(row_dict.get(id_col) or "").strip()
        title = str(row_dict.get(title_col) or "").strip()
        image_url = str(row_dict.get(url_col) or "").strip()
        raw_features = str(row_dict.get(feat_col) or "").strip()

        if not image_url or image_url.lower() in ["none", "null", ""]:
            return False # Игнорируем пустые ссылки без генерации ошибки

        if not product_id:
            raise ValueError("Отсутствует Код/Артикул товара при наличии ссылки на фото")

        features_list = [line.strip() for line in raw_features.split("\n") if line.strip()]
        task_id = f"task_xml_{uuid.uuid4().hex[:12]}"
        
        clean_id = "".join(c for c in product_id if c.isalnum() or c in ("-", "_")).rstrip()
        filename = f"{clean_id}.jpg"
        
        ctx = {
            "sys_mode": mode,
            "api_key": key,
            "source_path": image_url,
            "output_path": os.path.join(output_dir, filename),
            "shadow": shadow,
            "scale": scale,
            "watermark_pos": w_pos,
            "meta": {
                "product_id": product_id,
                "title": title,
                "features": features_list
            }
        }

        update_task_status(task_id, "PENDING", {"file": image_url, "product_id": product_id})
        TASK_QUEUE.put_nowait({"task_id": task_id, "ctx": ctx})
        stats["successfully_queued"] += 1
        return True
