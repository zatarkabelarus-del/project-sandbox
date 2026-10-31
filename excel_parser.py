import os
import csv
import uuid
import logging
import gc
from typing import Dict, List, Optional, Union

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
    Поддерживает динамическое чтение N колонок текстов для слайдов инфографики.
    """

    def __init__(self):
        pass

    def parse_and_queue(
        self,
        file_path: str,
        id_column_name: str,       
        title_column_name: str,    
        url_column_name: str,      
        features_columns: Union[str, List[str]], 
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

        ext = os.path.splitext(file_path)[1].lower()
        
        stats = {
            "successfully_queued": 0,
            "failed_count": 0,
            "failed_rows_details": []
        }

        if isinstance(features_columns, str):
            feat_cols = [c.strip() for c in features_columns.split(",") if c.strip()]
        else:
            feat_cols = [str(c).strip() for c in features_columns if c]

        if ext == ".csv":
            self._parse_csv(file_path, id_column_name, title_column_name, url_column_name, feat_cols, output_dir, sys_mode, api_key, shadow, scale, watermark_pos, stats)
        elif ext in [".xlsx", ".xlsm"]:
            self._parse_xlsx(file_path, id_column_name, title_column_name, url_column_name, feat_cols, output_dir, sys_mode, api_key, shadow, scale, watermark_pos, stats)
        else:
            raise InvalidImageError(f"Неподдерживаемый формат файла прайс-листа: {ext}")

        logger.info(f"[📊 ПАРСЕР ЗАВЕРШЕН]: УСПЕХ: {stats['successfully_queued']}, ОШИБОК: {stats['failed_count']}")
        return stats

    def _parse_csv(self, file_path: str, id_col: str, title_col: str, url_col: str, feat_cols: List[str], output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict):
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
                    self._process_row_data(
                        row_dict=row, id_col=id_col, title_col=title_col, url_col=url_col,
                        feat_cols=feat_cols, output_dir=output_dir, mode=mode, key=key,
                        shadow=shadow, scale=scale, w_pos=w_pos, stats=stats
                    )
                except Exception as row_err:
                    stats["failed_count"] += 1
                    stats["failed_rows_details"].append(f"Строка {current_row_index}: {str(row_err)}")
                    logger.error(f"[⚠️ СБОЙ CSV] Строка {current_row_index}: {str(row_err)}")

    def _parse_xlsx(self, file_path: str, id_col: str, title_col: str, url_col: str, feat_cols: List[str], output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict):
        if openpyxl is None:
            raise ImportError("Необходимо установить openpyxl")

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet = wb.active
            headers_map = {}
            
            for row_idx, row_cells in enumerate(sheet.iter_rows(values_only=True), start=1):
                if row_idx == 1:
                    headers_map = {str(h).strip(): idx for idx, h in enumerate(row_cells) if h is not None}
                    for col_name in [id_col, title_col, url_col]:
                        if col_name not in headers_map:
                            raise KeyError(f"Обязательная колонка '{col_name}' не найдена в заголовках.")
                    continue

                if not any(row_cells): 
                    continue

                try:
                    row_dict = {}
                    for col_name, idx in headers_map.items():
                        if idx < len(row_cells):
                            row_dict[col_name] = row_cells[idx]

                    self._process_row_data(
                        row_dict=row_dict, id_col=id_col, title_col=title_col, url_col=url_col,
                        feat_cols=feat_cols, output_dir=output_dir, mode=mode, key=key,
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

    def _process_row_data(self, row_dict: Dict[str, any], id_col: str, title_col: str, url_col: str, feat_cols: List[str], output_dir: str, mode: str, key: str, shadow: bool, scale: float, w_pos: str, stats: dict) -> bool:
        product_id = str(row_dict.get(id_col) or "").strip()
        title = str(row_dict.get(title_col) or "").strip()
        image_url = str(row_dict.get(url_col) or "").strip()

        if not image_url or image_url.lower() in ["none", "null", ""]:
            return False 

        if not product_id:
            raise ValueError("Отсутствует Код/Артикул товара при наличии ссылки на photo")

        slides_infographics = []
        for c_name in feat_cols:
            raw_val = str(row_dict.get(c_name) or "").strip()
            lines = []
            for line in raw_val.split("\n"):
                clean_line = line.strip()
                if clean_line:
                    lines.append({
                        "text": clean_line,
                        "is_caps": clean_line.isupper()
                    })
            slides_infographics.append(lines)

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
                "slides_infographics": slides_infographics
            }
        }

        update_task_status(task_id, "PENDING", {"file": image_url, "product_id": product_id})
        TASK_QUEUE.put_nowait({"task_id": task_id, "ctx": ctx})
        stats["successfully_queued"] += 1
        return True
