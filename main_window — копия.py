import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QTableWidget, QTableWidgetItem, 
                             QPushButton, QLabel, QHeaderView, QMessageBox, QDialog,
                             QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog,
                             QTabWidget, QGroupBox, QLineEdit, QCheckBox, QStyledItemDelegate,
                             QStyle)
from PySide6.QtGui import Qt, QColor, QKeySequence, QGuiApplication, QTextDocument
from PySide6.QtCore import QObject, QThread, Signal, Slot


class HTMLDelegate(QStyledItemDelegate):
    """Сверхскоростной нативный делегат для посимвольной HTML-раскраски цен конкурентов через |"""
    def paint(self, painter, option, index):
        options = option
        self.initStyleOption(options, index)
        
        painter.save()
        doc = QTextDocument()
        
        # Получаем HTML-текст из ячейки
        html_text = str(index.data(Qt.DisplayRole))
        
        # Проверяем, выделена ли текущая строка в данный момент
        if options.state & QStyle.State_Selected:
            # Если строка выделена синим, очищаем цветные теги и красим всё в белый. 
            # Цены 'под заказ' (содержащие 'зак' или 'x') выделяем жирным (bold)
            html_text = html_text.replace("color: #e74c3c; font-weight: bold;", "color: #ffffff; font-weight: bold;")
            html_text = html_text.replace("color: #2c3e50;", "color: #ffffff; font-weight: normal;")
            # Страховка для очистки любых других темных тегов, если они попадут
            html_text = html_text.replace("color:#e74c3c;", "color:#ffffff; font-weight:bold;")
            html_text = html_text.replace("color:#2c3e50;", "color:#ffffff;")
            
        doc.setHtml(f"<div style='font-family: Segoe UI, Arial; font-size: 13px;'>{html_text}</div>")
        
        # Сдвигаем painter под размеры ячейки
        painter.translate(options.rect.x(), options.rect.y())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        options = option
        self.initStyleOption(options, index)
        doc = QTextDocument()
        doc.setHtml(str(index.data(Qt.DisplayRole)))
        return doc.size().toSize()

# Добавлены Core-компоненты для работы с потоками и сигналами
from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
# Добавлен импорт метода переоценки из бэкенда
from database import get_connection, save_supplier_mapping, get_supplier_mapping
import woocommerce_sync
from supplier_parser import SupplierParser
import re
from difflib import SequenceMatcher
# Добавить к остальным импортам в самом верху main_window.py:
from competitor_worker import LiveSearchWorker

def calculate_similarity(our_name, competitor_name):
    """Рассчитывает процент сходства названий с жестким контролем моделей/цифр"""
    our_clean = str(our_name).lower().strip()
    comp_clean = str(competitor_name).lower().strip()
    
    # 1. Вытаскиваем все цифры (модели: 4500, 180, 5200) из нашего товара
    our_numbers = re.findall(r'\d+', our_clean)
    
    # 2. Считаем базовое сходство слов через встроенный difflib
    base_ratio = SequenceMatcher(None, our_clean, comp_clean).ratio() * 100
    
    # 3. Жесткий фильтр: если у нас в SKU/имени есть цифра, а у конкурента её нет,
    # значит это принципиально другая запчасть. Срезаем рейтинг до минимума.
    for num in our_numbers:
        if num not in comp_clean:
            return min(base_ratio, 15.0) # Жесткий штраф
            
    return round(base_ratio, 1)

class CompetitorMappingDialog(QDialog):
    def __init__(self, product_sku, product_name, purchase_price, current_retail, search_results, parent=None):
        """Конструктор принимает цены из таблицы и строит расширенную инфо-панель"""
        super().__init__(parent)
        self.setWindowTitle("Результаты сопоставления товара с конкурентами")
        self.resize(800, 570) # Слегка увеличим высоту под новый ряд цен
        
        self.product_sku = product_sku
        self.product_name = product_name
        self.purchase_price = purchase_price
        self.current_retail = current_retail
        
        main_layout = QVBoxLayout(self)
        
        # 1. ВЕРХНЯЯ ПАНЕЛЬ: Инфо о нашем товаре и его текущих ценах
        info_layout = QVBoxLayout()
        
        # Ряд 1: Название товара
        self.name_label = QLabel(f"<b>Наш товар:</b> {self.product_name}")
        self.name_label.setStyleSheet("font-size: 14px; color: #2c3e50;")
        info_layout.addWidget(self.name_label)
        
        # Ряд 2: Артикул + Цена закупки + Текущая розница в одну аккуратную строку
        prices_layout = QHBoxLayout()
        
        self.sku_label = QLabel(f"<b>Артикул:</b> <span style='color:#e74c3c; font-weight:bold;'>{self.product_sku}</span>")
        self.sku_label.setStyleSheet("font-size: 13px;")
        prices_layout.addWidget(self.sku_label)
        
        prices_layout.addSpacing(25)
        
        # Выделяем закупку бордовым цветом
        self.purchase_label = QLabel(f"<b>Цена закупки:</b> <span style='color:#c0392b; font-weight:bold;'>{self.purchase_price} руб.</span>")
        self.purchase_label.setStyleSheet("font-size: 13px;")
        prices_layout.addWidget(self.purchase_label)
        
        prices_layout.addSpacing(25)
        
        # Выделяем розницу синим цветом
        self.retail_label = QLabel(f"<b>Текущая розница:</b> <span style='color:#2980b9; font-weight:bold;'>{self.current_retail} руб.</span>")
        self.retail_label.setStyleSheet("font-size: 13px;")
        prices_layout.addWidget(self.retail_label)
        
        prices_layout.addStretch() # Прижимает всю строку цен влево
        info_layout.addLayout(prices_layout)
        
        main_layout.addLayout(info_layout)
        
        # 2. ЦЕНТРАЛЬНАЯ ЧАСТЬ: Динамические вкладки конкурентов
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)        
        
        # Определяем текущий режим парсинга из родительского окна
        self.current_mode = "Запасные части (NS / Rentall)"
        if parent and hasattr(parent, 'parsing_mode_selector'):
            self.current_mode = parent.parsing_mode_selector.currentText()
            
        # Списки виджетов и словари URL-адресов для точечного извлечения данных
        self.lists_map = {} # Индекс вкладки -> QListWidget
        self.urls_map = {}  # Индекс вкладки -> { Строка списка -> Реальный URL }
        self.names_map = {} # Индекс вкладки -> Системное имя конкурента (NS-Service, Agrox, и т.д.)
        
        # Заполняем вкладки в зависимости от выбранного глобального режима
        if "садовая техника" in self.current_mode.lower():
            # Режим Садовая техника: Создаем 3 независимые вкладки
            self._create_tab(0, "Agrox.by", "Agrox", search_results.get("agrox", []))
            self._create_tab(1, "Каталог Onliner", "Onliner", search_results.get("onliner", []))
            self._create_tab(2, "Shop.by", "Shop.by", search_results.get("shop", []))
        else:
            # Режим Запасные части: Сохраняем базовые 2 вкладки
            self._create_tab(0, "NS-Service.by", "NS-Service", search_results.get("ns_service", []))
            self._create_tab(1, "Rentall.by", "Rentall", search_results.get("rentall", []))
        
        # 3. НИЖНЯЯ ПАНЕЛЬ: Кнопки управления
        self.btn_open_browser = QPushButton("Открыть в браузере")
        self.btn_confirm = QPushButton("Подтвердить связь")
        self.btn_cancel = QPushButton("Отмена")
        
        self.btn_open_browser.setStyleSheet("background-color: #34495e; color: white; padding: 6px; font-weight: bold;")
        self.btn_confirm.setStyleSheet("background-color: #27ae60; color: white; padding: 6px; font-weight: bold;")
        self.btn_cancel.setStyleSheet("background-color: #95a5a6; color: white; padding: 6px;")
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.btn_open_browser)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_confirm)
        button_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(button_layout)
        
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_open_browser.clicked.connect(self.on_open_browser_clicked)

# НАЧАЛО ИЗМЕНЕНИЙ: main_window.py -> класс CompetitorMappingDialog -> метод _create_tab
    def _create_tab(self, tab_index, tab_title, competitor_name, items_list):
        """Вспомогательный метод динамического построения и наполнения отдельной вкладки"""
        list_widget = QListWidget()
        
        # 🎯 Включаем перенос длинных строк штатными средствами Qt
        list_widget.setWordWrap(True)
        list_widget.setTextElideMode(Qt.ElideNone)
        
        self.tabs.addTab(list_widget, tab_title)
        
        self.lists_map[tab_index] = list_widget
        self.urls_map[tab_index] = {}
        self.names_map[tab_index] = competitor_name
        
        if items_list:
            list_widget.setUpdatesEnabled(False)
            
            for idx, item in enumerate(items_list):
                # 🎯 НАДЁЖНОЕ И ЧИСТOЕ ИЗВЛЕЧЕНИЕ ДАННЫХ ДЛЯ ОКНА СОПОСТАВЛЕНИЯ СТРОГО ПО ТЗ
                p_val = item.get("price", "0.00")
                p_status = str(item.get("status", "в наличии")).lower().strip()
                p_rating = item.get("rating", "—")
                
                # Если парсер уже нашёл конкретного продавца (для Onliner/Shop) — берём его, иначе сам сайт
                p_seller = item.get("seller", "").strip()
                if not p_seller or p_seller == "Не определён":
                    p_seller = competitor_name

                # Профессиональная очистка цены от букв и пробелов перед проверкой на ноль
                if p_val is None or str(p_val).strip() == "" or str(p_val).strip() == "0":
                    float_p = 0.0
                else:
                    clean_price_digits = "".join(c for c in str(p_val) if c.isdigit() or c in ".,").replace(",", ".")
                    try:
                        float_p = float(clean_price_digits) if clean_price_digits else 0.0
                    except ValueError:
                        float_p = 0.0
                    
                # Окончательно определяем маркеры отображения цены
                if float_p <= 0.0:
                    p_status = "под заказ"
                    display_price_str = "x (зак)"
                elif "под заказ" in p_status or "нет в наличии" in p_status:
                    display_price_str = f"{float_p:.2f} (зак)"
                else:
                    display_price_str = f"{float_p:.2f}"
                
                # Формируем красивую и информативную строку для менеджера
                if item.get("sku") and item["sku"] not in ("Onliner", "Shop.by"):
                    display_text = f"[{item['similarity']}%] Продавец: {p_seller} [Рейтинг: {p_rating}] | [Арт: {item['sku']}] {item['name']} | Цена: {display_price_str} руб."
                else:
                    display_text = f"[{item['similarity']}%] Продавец: {p_seller} [Рейтинг: {p_rating}] | {item['name']} | Цена: {display_price_str} руб."
                
                list_item = QListWidgetItem(display_text)
                
                # 🎯 УПРАВЛЕНИЕ ЦВЕТОМ ТЕКСТА ЦЕНЫ/СТРОКИ СТРОГО ПО ТЗ:
                # зелёный – в наличии, чёрный – не определён, красный – под заказ
                from PySide6.QtGui import QColor
                if p_status == "под заказ" or float_p <= 0.0:
                    list_item.setForeground(QColor(231, 76, 60))  # Красный
                elif p_status == "в наличии":
                    list_item.setForeground(QColor(39, 174, 96))   # Зелёный
                else:
                    list_item.setForeground(QColor(44, 62, 80))    # Чёрный (не определён)
                
                base_size = list_item.sizeHint()
                if base_size.height() > 0:
                    base_size.setHeight(base_size.height() + 14)
                    list_item.setSizeHint(base_size)
                
                list_widget.addItem(list_item)
                
                # Сохраняем обновленные метаданные для передачи в БД при клике на подтверждение
                item["status"] = p_status
                item["seller"] = p_seller
                self.urls_map[tab_index][idx] = item
            
            list_widget.setUpdatesEnabled(True)
        else:
            list_widget.addItem(QListWidgetItem(f"Ничего не найдено на {tab_title}"))
# КОНЕЦ ИЗМЕНЕНИЙ: main_window.py -> класс CompetitorMappingDialog -> метод _create_tab

    def on_open_browser_clicked(self):
        """Открывает реальную ссылку выбранного конкурентного товара в браузере Windows"""
        import webbrowser
        current_tab = self.tabs.currentIndex()
        
        if current_tab in self.lists_map:
            current_list = self.lists_map[current_tab]
            url_map = self.urls_map[current_tab]
            selected_row = current_list.currentRow()
            
            # Если строка реально выделена — открываем точную прямую ссылку карточки этого товара
            if selected_row != -1 and selected_row in url_map:
                webbrowser.open(url_map[selected_row]["url"])
                return
                
        # 🎯 ИСПРАВЛЕНИЕ БАГА: Если строка не выбрана, генерируем идеальную поисковую ссылку
        import urllib.parse
        art = str(self.product_sku).strip()
        search_query = art if (art and art != "Нет SKU") else str(self.product_name).strip()
        encoded_query = urllib.parse.quote(search_query)
        
        comp_name = self.names_map.get(current_tab, "Agrox")
        
        if comp_name == "Agrox":
            fallback_url = f"https://agrox.by{urllib.parse.quote_plus(search_query)}"
        elif comp_name == "Onliner":
            fallback_url = f"https://onliner.by{encoded_query}"
        elif comp_name == "Shop.by":
            fallback_url = f"https://shop.by{encoded_query}"
        elif comp_name == "NS-Service":
            fallback_url = f"https://ns-service.by{encoded_query}"
        else:
            fallback_url = f"https://rentall.by{encoded_query}"
            
        print(f"[UI Браузер] Строка не выбрана. Перенаправление на общий поиск: {fallback_url}")
        webbrowser.open(fallback_url)
            
    def get_selected_mappings(self):
        """Сканирует ВСЕ вкладки и возвращает строго те связи, которые пользователь РЕАЛЬНО КЛИКНУЛ"""
        selected_results = []
        
        # Обходим все фактически созданные вкладки диалогового окна
        for tab_index in range(self.tabs.count()):
            if tab_index in self.lists_map:
                current_list = self.lists_map[tab_index]
                url_map = self.urls_map[tab_index]
                competitor = self.names_map[tab_index]
                
                # 🎯 СТРОГАЯ ПРОВЕРКА: Берем только фактически выделенные пользователем элементы
                selected_items = current_list.selectedItems()
                if not selected_items:
                    continue # Если во вкладке ничего не кликнули мышкой — полностью игнорируем её
                    
                clicked_item = selected_items[0]
                # Получаем реальный индекс строки кликнутого элемента в списке
                selected_row = current_list.row(clicked_item)
                
                if selected_row != -1 and selected_row in url_map:
                    txt = clicked_item.text()
                    
                    # Игнорируем заглушки "Ничего не найдено"
                    if "Ничего не найдено" in txt:
                        continue
                        
                    # Извлекаем данные напрямую из сохраненного объекта метаданных товара
                    target_item_obj = url_map[selected_row]
                    parsed_price = target_item_obj.get("price", "0.00")
                    calculated_status = target_item_obj.get("status", "в наличии")
                        
                    selected_results.append({
                        "competitor": competitor,
                        "url": target_item_obj.get("url", ""),
                        "text": txt,
                        "price": parsed_price,
                        "status": calculated_status # Передаем реальный статус прямо в СУБД!
                    })
                    
        return selected_results

class RepriceWorker(QObject):
    """Фоновый воркер для раздельного обновления закупок и массовой переоценки розницы конкурентов по спискам"""
    finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, mode="purchases", list_id=None, parent=None):
        super().__init__(parent)
        self.mode = mode       # Режим работы: "purchases" или "repricing"
        self.list_id = list_id # ID списка товаров для обработки

    @Slot()
    def run(self):
        """Метод выполняется в отдельном потоке, изолируя логику сбора данных по конкретному списку"""
        import requests
        import json
        from requests.adapters import HTTPAdapter
        from urllib3.util import Retry
        from database import get_connection
        
        try:
            if self.list_id is None:
                print("[Фоновый поток] Ошибка: Не передан ID списка. Прерывание операции.")
                self.finished.emit()
                return

            conn = get_connection()
            cursor = conn.cursor()
            
            # 1. ШАГ: Извлекаем базовый список продуктов СТРОГО ДЛЯ ВЫБРАННОГО СПИСКА
            cursor.execute("SELECT id, sku FROM my_products WHERE list_id = ?", (self.list_id,))
            db_products = cursor.fetchall()
            
            if not db_products:
                print(f"[Фоновый поток] Локальная база товаров для списка ID {self.list_id} пуста. Нечего обновлять.")
                conn.close()
                self.finished.emit()
                return
                
            articles_to_request = []
            sku_to_db_id = {}
            
            for db_id, raw_sku in db_products:
                if not raw_sku:
                    continue
                art_str = str(raw_sku).strip()
                articles_to_request.append(art_str)
                sku_to_db_id[art_str] = db_id

            domain_part = "script." + "google" + ".com"
            path_part = "/macros/s/"
            macro_id = "AKfycby1ftyyrC1Lt11F1FWG02UDate7j0XRhZKHeXTmFsXTkUDORAr8AGkAMQtpo87H__4q"
            action_part = "/exec"
            WEB_APP_URL = f"https://{domain_part}{path_part}{macro_id}{action_part}"
            headers = {"Content-Type": "application/json"}
            
            # Настраиваем умную сессию с автоповторами для защиты от моргания интернета
            session = requests.Session()
            retries = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))
            
            # =========================================================================
            # ВЕТВЛЕНИЕ ПО РЕЖИМАМ РАБОТЫ
            # =========================================================================
            if self.mode == "purchases":
                print(f"\n[Фоновый поток] Режим: ТОЧЕЧНЫЙ СБОР ЗАКУПОК ПОСТАВЩИКОВ ДЛЯ СПИСКА ID {self.list_id}...")
                payload = {
                    "action": "get_purchases",
                    "articles": articles_to_request
                }
                
                print("[Фоновый поток] Отправка POST-запроса в облако...")
                response = session.post(WEB_APP_URL, json=payload, headers=headers, timeout=45)
                response.raise_for_status()
                
                server_response = response.json()
                if not server_response or "error" in server_response:
                    raise Exception(f"Ошибка Google: {server_response.get('error', 'Пустой ответ')}")
                
                matched_prices = server_response.get("prices", {})
                
                updated_count = 0
                for art_str, db_id in sku_to_db_id.items():
                    if art_str in matched_prices:
                        info = matched_prices[art_str]
                        cost = info.get('price', 0)
                        source_name = info.get('source', 'НЕ НАЙДЕН')
                        
                        if cost > 0:
                            cursor.execute("""
                                UPDATE my_products 
                                SET purchase_price = ?, supplier_source = ? 
                                WHERE id = ?
                            """, (cost, source_name, db_id))
                            updated_count += 1
                
                conn.commit()
                print(f"[Фоновый поток] УСПЕХ! Обновлены закупные цены для {updated_count} товаров.")
            elif self.mode == "repricing":
                print(f"\n[Фоновый поток] Режим: ИЗОЛИРОВАННЫЙ РЕПРАЙСИНГ РОЗНИЦЫ ДЛЯ СПИСКА ID {self.list_id}...")
                
                try:
                    cursor.execute("""
                        SELECT cl.product_id, cl.competitor_url 
                        FROM competitor_links cl
                        JOIN my_products p ON p.id = cl.product_id
                        WHERE p.list_id = ?
                    """, (self.list_id,))
                    links_rows = cursor.fetchall()
                    db_competitor_links = {}
                    for pid, url in links_rows:
                        if pid not in db_competitor_links:
                            db_competitor_links[pid] = []
                        db_competitor_links[pid].append(url)
                except Exception as e:
                    print(f"[Фоновый поток] Ошибка чтения links для списка {self.list_id}: {e}")
                    db_competitor_links = {}

                payload = {
                    "action": "get_competitors",
                    "competitor_links": db_competitor_links
                }
                
                print("[Фоновый поток] Отправка ссылок конкурентов на парсинг в облако...")
                try:
                    # 🎯 НАСТРОЙКА: Оптимальный таймаут 3 минуты для больших групп товаров
                    response = session.post(WEB_APP_URL, json=payload, headers=headers, timeout=180)
                    response.raise_for_status()
                    print("[REPRICE WORKER] Ответ от облачного скрипта успешно получен.")
                except requests.exceptions.Timeout:
                    print("[REPRICE WORKER] Превышено время ожидания ответа от облачного скрипта (Таймаут).")
                    session.close()
                    self.error_occurred.emit("Облачный скрипт макроса не ответил. Сервер Google перегружен.")
                    return
                except requests.exceptions.RequestException as net_err:
                    print(f"[REPRICE WORKER] Сетевая ошибка при связи с облаком: {net_err}")
                    session.close()
                    self.error_occurred.emit(f"Сбой сети при репрайсинге (Google Script недоступен): {net_err}")
                    return

                server_response = response.json()
                if not server_response or "error" in server_response:
                    raise Exception(f"Ошибка Google: {server_response.get('error', 'Пустой ответ')}")
                
                competitor_prices = server_response.get("competitor_prices", {})
                
                if competitor_prices:
                    for url, fresh_price in competitor_prices.items():
                        try:
                            cursor.execute("""
                                UPDATE competitor_links 
                                SET last_seen_price = ?, last_updated = CURRENT_TIMESTAMP
                                WHERE competitor_url = ?
                            """, (float(fresh_price), url))
                        except Exception as link_err:
                            print(f"[Фоновый поток] Ошибка更新 розницы по ссылке {url}: {link_err}")
                
                conn.commit()
                print("[Фоновый поток] Розничные цены конкурентов успешно зафиксированы в СУБД.")
                
                # Автовыгрузка отключена, просто идем дальше
                pass

            # Корректно закрываем сессию и соединения
            session.close()

            # Корректно закрываем сессию и соединения
            session.close()
            conn.close()
            self.finished.emit()
            
        except Exception as e:
            import traceback
            print("\n!!! КРИТИЧЕСКАЯ ОШИБКА В РАЗДЕЛЕННОМ ФОНОВОМ ПОТОКЕ !!!")
            traceback.printexc()
            if 'session' in locals():
                try: session.close()
                except: pass
            if 'conn' in locals():
                try: conn.close()
                except: pass
            
            full_error_log = f"Критическое исключение: {str(e)}\n\nСистемная трассировка:\n{traceback.format_exc()}"
            self.error_occurred.emit(full_error_log)

class ImportDialog(QDialog):
    """Окно импорта категорий напрямую с WooCommerce"""
    def __init__(self, parent=None, list_id=None):
        super().__init__(parent)
        self.list_id = list_id
        self.setWindowTitle("Импорт категорий из WooCommerce")
        self.resize(450, 550) # Слегка увеличим под новые элементы
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите категории для импорта в текущий список:"))
        
        # 🎯 ОПЦИЯ МАССОВОГО ВЫДЕЛЕНИЯ КАТЕГОРИЙ СТРОГО ПО ТЗ
        self.chk_select_all_cats = QCheckBox("Выбрать все категории")
        self.chk_select_all_cats.setStyleSheet("font-weight: bold; color: #34495e; margin-bottom: 5px;")
        self.chk_select_all_cats.stateChanged.connect(self.toggle_all_categories)
        layout.addWidget(self.chk_select_all_cats)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list_widget)
        
        # 🎯 ИЗМЕНЕН ТЕКСТ ЛЕГЕНДЫ ФИЛЬТРА ПОД ФАКТИЧЕСКИЙ ОСТАТОК (КОЛИЧЕСТВО >= 1)
        self.chk_only_instock = QCheckBox("Загружать товары только при количестве ≥ 1 шт.")
        self.chk_only_instock.setStyleSheet("font-weight: bold; color: #27ae60; margin: 5px 0px;")
        self.chk_only_instock.setChecked(True)
        layout.addWidget(self.chk_only_instock)
        
        self.btn_do_import = QPushButton("📥 Запустить импорт")
        self.btn_do_import.clicked.connect(self.start_import)
        layout.addWidget(self.btn_do_import)
        
        self.load_categories()

    def toggle_all_categories(self, state):
        """Слот мгновенного выделения или снятия галочек со всех категорий в списке"""
        target_state = Qt.Checked if state == 2 or state == Qt.Checked else Qt.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(target_state)

    def load_categories(self):
        categories = woocommerce_sync.get_woocommerce_categories()
        if not categories:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить категории с сайта.")
            self.reject()
            return
            
        for cat in categories:
            item = QListWidgetItem(f"{cat['name']} (ID: {cat['id']})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, cat['id'])
            self.list_widget.addItem(item)

    def start_import(self):
        selected_cats = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_cats.append(item.data(Qt.UserRole))
                
        if not selected_cats:
            QMessageBox.warning(self, "Внимание", "Выберите хотя бы одну категорию!")
            return
            
        # Считываем состояние нашего нового фильтра перед циклом
        only_in_stock_flag = self.chk_only_instock.isChecked()
            
        self.btn_do_import.setEnabled(False)
        self.btn_do_import.setText("⏳ Скачивание товаров...")
        QApplication.processEvents()
        
        total = 0
        for cat_id in selected_cats:
            # 🎯 ПЕРЕДАЕМ ПАРАМЕТР ФИЛЬТРАЦИИ НАПРЯМУЮ В ОБНОВЛЕННЫЙ БЭКЕНД
            total += woocommerce_sync.import_products_by_category(
                category_id=cat_id, 
                list_id=self.list_id, 
                only_in_stock=only_in_stock_flag
            )
            
        QMessageBox.information(self, "Готово", f"Импорт завершен!\nУспешно загружено/обновлено товаров: {total}")
        self.accept()

class RepriceSettingsDialog(QDialog):
    """Модальное окно параметров математического репрайсинга товаров"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = parent  # Жестко сохраняем прямую ссылку на MainWindow
        self.setWindowTitle("Параметры репрайсинга товаров")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        info_lbl = QLabel("<b>Настройте параметры расчёта цен для выбранного списка:</b>")
        info_lbl.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(info_lbl)
        
        from PySide6.QtWidgets import QFormLayout
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        # Гарантированно вытаскиваем текст из памяти главного окна
        init_avail = self.main_win.saved_dumping_avail if (self.main_win and hasattr(self.main_win, 'saved_dumping_avail')) else "1.0"
        init_order = self.main_win.saved_dumping_order if (self.main_win and hasattr(self.main_win, 'saved_dumping_order')) else "-1.0"
        init_no_comp = self.main_win.saved_no_competitors if (self.main_win and hasattr(self.main_win, 'saved_no_competitors')) else "25.0"
        init_min_marg = self.main_win.saved_min_margin if (self.main_win and hasattr(self.main_win, 'saved_min_margin')) else "20.0"
        
        self.input_dumping_avail = QLineEdit(init_avail)
        form_layout.addRow("Демпинг от мин. цены конкурентов В НАЛИЧИИ %:", self.input_dumping_avail)
        
        self.input_dumping_order = QLineEdit(init_order)
        self.input_dumping_order.setPlaceholderText("Минус (-) вниз, Плюс (+) вверх")
        form_layout.addRow("Демпинг от мин. цены конкурентов ПОД ЗАКАЗ % (+-):", self.input_dumping_order)
        
        self.input_no_competitors = QLineEdit(init_no_comp)
        form_layout.addRow("Наценка при отсутствии цен конкурентов %:", self.input_no_competitors)
        
        self.input_min_margin = QLineEdit(init_min_marg)
        form_layout.addRow("Контроль минимальной наценки %:", self.input_min_margin)
        
        layout.addLayout(form_layout)
        layout.addSpacing(15)
        
        self.btn_run = QPushButton("🚀 Запустить репрайсинг")
        self.btn_run.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 8px; font-size: 13px;")
        self.btn_run.clicked.connect(self.validate_and_accept)
        layout.addWidget(self.btn_run)
        
    def validate_and_accept(self):
        """Проверка заполнения всех полей перед закрытием окна"""
        try:
            # Парсим введенный текст в числа для проверки на ошибки
            da = float(self.input_dumping_avail.text().replace(',', '.'))
            do = float(self.input_dumping_order.text().replace(',', '.'))
            nc = float(self.input_no_competitors.text().replace(',', '.'))
            mm = float(self.input_min_margin.text().replace(',', '.'))
            
            # Напрямую перезаписываем переменные памяти в MainWindow через сохраненную ссылку
            if self.main_win:
                self.main_win.saved_dumping_avail = self.input_dumping_avail.text()
                self.main_win.saved_dumping_order = self.input_dumping_order.text()
                self.main_win.saved_no_competitors = self.input_no_competitors.text()
                self.main_win.saved_min_margin = self.input_min_margin.text()
                
                # 🎯 ДОБАВЛЕНО: Автоматическое сохранение параметров в реестр Windows
                from PySide6.QtCore import QSettings
                settings = QSettings("RepricerApp", "MainWindowSettings")
                settings.setValue("saved_dumping_avail", self.input_dumping_avail.text())
                settings.setValue("saved_dumping_order", self.input_dumping_order.text())
                settings.setValue("saved_no_competitors", self.input_no_competitors.text())
                settings.setValue("saved_min_margin", self.input_min_margin.text())
            
            self.results = {
                "dumping_avail": da,
                "dumping_order": do,
                "no_competitors": nc,
                "min_margin": mm
            }
            self.accept()
        except ValueError:
            QMessageBox.critical(self, "Ошибка заполнения", "Пожалуйста, заполните ВСЕ поля числовыми значениями.\nИспользуйте знак минус (-) для демпинга под заказ вниз.")


class LoginDialog(QDialog):
    """Модальное защищённое окно авторизации при запуске EXE-приложения"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Авторизация в системе")
        self.setFixedWidth(350)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        lbl = QLabel("<b>Введите пароль для входа в Репрайсер:</b>")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setAlignment(Qt.AlignCenter)
        self.pwd_input.setStyleSheet("padding: 5px; font-size: 14px;")
        layout.addWidget(self.pwd_input)
        
        btn_layout = QHBoxLayout()
        self.btn_login = QPushButton("Войти")
        self.btn_login.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px;")
        self.btn_login.clicked.connect(self.check_password)
        
        self.btn_exit = QPushButton("Выход")
        self.btn_exit.setStyleSheet("background-color: #e74c3c; color: white; padding: 5px;")
        self.btn_exit.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_exit)
        layout.addLayout(btn_layout)
        
    def check_password(self):
        entered = self.pwd_input.text().strip()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pwd_hash FROM app_credentials WHERE id = 1")
        row = cursor.fetchone()
        db_pwd = row[0] if row else "1234"
        conn.close()
        
        if entered == db_pwd:
            self.accept()
        else:
            QMessageBox.critical(self, "Ошибка доступа", "Введён неверный пароль! Доступ заблокирован.")
            self.pwd_input.clear()
            self.pwd_input.setFocus()

class MainWindow(QMainWindow):
    # 🎯 СОЗДАЕМ БЕЗОПАСНЫЙ СИГНАЛ ДЛЯ СИНХРОНИЗАЦИИ ПОТОКОВ UI
    all_search_threads_finished = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Репрайсер WooCommerce v1.0")
        self.resize(1200, 600)

        # Ссылки на фоновый поток и воркер переоценки
        self.reprice_thread = None
        self.reprice_worker = None

        # 🎯 ДОБАВЛЕНО: Чтение последних использованных параметров из реестра Windows при старте
        from PySide6.QtCore import QSettings
        settings = QSettings("RepricerApp", "MainWindowSettings")
        
        self.saved_dumping_avail = str(settings.value("saved_dumping_avail", "1.0"))
        self.saved_dumping_order = str(settings.value("saved_dumping_order", "-1.0"))
        self.saved_no_competitors = str(settings.value("saved_no_competitors", "25.0"))
        self.saved_min_margin = str(settings.value("saved_min_margin", "20.0"))

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- ВЕРХНЯЯ ПАНЕЛЬ (Многорядный контейнер) ---
        header_container_layout = QVBoxLayout()
        
        # =========================================================================
        # 1-Й РЯД ЭЛЕМЕНТОВ УПРАВЛЕНИЯ
        # =========================================================================
        row1_layout = QHBoxLayout()
        row1_layout.addWidget(QLabel("Выбор списка товаров:"))
        
        self.list_selector = QComboBox()
        # 🎯 УВЕЛИЧИЛИ МИНИМАЛЬНУЮ ШИРИНУ НА 50% (БЫЛО 180 -> СТАЛО 270) СТРОГО ПО ТЗ
        self.list_selector.setMinimumWidth(270)
        self.list_selector.currentIndexChanged.connect(self.load_products_for_selected_list)
        
        # 🎯 ВОЗВРАЩАЕМ ОТСЛЕЖИВАНИЕ ПРАВОГО КЛИКА НА КОМБОБОКСЕ ВЫБОРА СПИСКОВ
        self.list_selector.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_selector.customContextMenuRequested.connect(self.show_list_selector_context_menu)
        
        row1_layout.addWidget(self.list_selector)

        self.btn_create_list = QPushButton("➕ Новый список")
        self.btn_create_list.clicked.connect(self.on_create_new_list_clicked)
        row1_layout.addWidget(self.btn_create_list)

        # === НАЧАЛО ИЗМЕНЕНИЙ: МНОГОФУНКЦИОНАЛЬНАЯ КНОПКА ИМПОРТА ===
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        self.btn_import = QPushButton("📥 Импорт товаров в программу")
        self.btn_import.setStyleSheet("padding: 4px 10px; font-weight: bold;")
        
        # Создаем выпадающее меню для кнопки
        import_menu = QMenu(self)
        
        action_import_woo = QAction("🌐 Импорт из WooCommerce", self)
        action_import_woo.triggered.connect(self.open_import_dialog)
        import_menu.addAction(action_import_woo)
        
        action_import_excel = QAction("📊 Импорт из Excel/CSV файла", self)
        action_import_excel.triggered.connect(self.open_excel_import_dialog)
        import_menu.addAction(action_import_excel)
        
        # Привязываем меню к кнопке
        self.btn_import.setMenu(import_menu)
        row1_layout.addWidget(self.btn_import)
        # === КОНЕЦ ИЗМЕНЕНИЙ: МНОГОФУНКЦИОНАЛЬНАЯ КНОПКА ИМПОРТА ===

        row1_layout.addSpacing(5)
        row1_layout.addWidget(QLabel("Парсинг:"))
        
        self.parsing_mode_selector = QComboBox()
        self.parsing_mode_selector.addItems([
            "Запасные части (NS / Rentall)",
            "Садовая техника (Agrox / Onliner / Shop)"
        ])
        row1_layout.addWidget(self.parsing_mode_selector)

        self.btn_bind_competitor = QPushButton("🔗 Связать с конкурентами")
        self.btn_bind_competitor.clicked.connect(self.on_bind_competitor_clicked)
        row1_layout.addWidget(self.btn_bind_competitor)

        self.btn_clear_table = QPushButton("🗑 Очистить таблицу")
        self.btn_clear_table.clicked.connect(self.clear_main_table)
        row1_layout.addWidget(self.btn_clear_table)        
        
        row1_layout.addSpacing(15)
        
        # 🎯 КНОПКА ЗАПУСКА ВСТРОЕННОЙ ИНСТРУКЦИИ
        self.btn_help = QPushButton("❓ Инструкция")
        self.btn_help.setStyleSheet("background-color: #34495e; color: white; font-weight: bold; padding: 3px 10px;")
        self.btn_help.clicked.connect(self.show_user_manual)
        row1_layout.addWidget(self.btn_help)
        
        row1_layout.addStretch()

        row1_layout.addSpacing(5)
        
        # Кнопка смены мастер-пароля
        self.btn_change_pwd = QPushButton("🔑 Задать пароль")
        self.btn_change_pwd.setStyleSheet("background-color: #7f8c8d; color: white; font-weight: bold; padding: 3px 10px;")
        self.btn_change_pwd.clicked.connect(self.change_app_password_logic)
        row1_layout.addWidget(self.btn_change_pwd)
        
        row1_layout.addStretch()

        # =========================================================================
        # 2-Й РЯД ЭЛЕМЕНТОВ УПРАВЛЕНИЯ (Бывший 3-й ряд: Дата слева, Кнопки запуска справа)
        # =========================================================================
        row2_layout = QHBoxLayout()
        
        # Дата последнего обновления (Прижата строго влево)
        self.lbl_last_update = QLabel("Дата последнего обновления Цен конкурентов: нет данных")
        self.lbl_last_update.setStyleSheet("font-weight: bold;")
        row2_layout.addWidget(self.lbl_last_update)

        row2_layout.addStretch() 

        # Кнопки запуска потоков (Прижаты строго вправо)
        self.btn_update_purchases = QPushButton("📥 Обновить закупки")
        self.btn_update_purchases.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 5px 12px;")
        self.btn_update_purchases.clicked.connect(self.start_purchases_thread)
        row2_layout.addWidget(self.btn_update_purchases)

        row2_layout.addSpacing(5)

        self.btn_start_repricing = QPushButton("🚀 Запустить переобход конкурентов")
        self.btn_start_repricing.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px 12px;")
        self.btn_start_repricing.clicked.connect(self.start_repricing_thread)
        row2_layout.addWidget(self.btn_start_repricing)

        # =========================================================================
        # 3-Й РЯД ЭЛЕМЕНТОВ УПРАВЛЕНИЯ (Действия + Маржа/Демпинг + Выделить все справа)
        # =========================================================================
        row3_layout = QHBoxLayout()
        
        self.bulk_action_selector = QComboBox()
        self.bulk_action_selector.setMinimumWidth(260)
        self.bulk_action_selector.addItems([
            "работать с выделенными ячейками", "скрыть выделенные ячейки",
            "записать цены в woocommerce и в файл", "записать цены в файл"
        ])
        row3_layout.addWidget(self.bulk_action_selector)
        
        self.btn_apply_bulk = QPushButton("Применить")
        self.btn_apply_bulk.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 3px 10px;")
        self.btn_apply_bulk.clicked.connect(self.execute_selected_bulk_action)
        row3_layout.addWidget(self.btn_apply_bulk)
        
        # Переименовываем и переносим кнопку в 3-й ряд управления
        self.btn_order_repricing = QPushButton("📦 Репрайсинг товаров")
        self.btn_order_repricing.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold; padding: 5px 14px;")
        self.btn_order_repricing.clicked.connect(self.start_order_repricing_logic)
        row3_layout.addWidget(self.btn_order_repricing)

        row3_layout.addSpacing(20) 
        
        self.chk_hide_zeros = QCheckBox("Скрыть значения цены закупки 0.00")
        self.chk_hide_zeros.setStyleSheet("font-weight: bold; color: #c0392b;") 
        self.chk_hide_zeros.stateChanged.connect(self.filter_zero_purchase_rows)
        row3_layout.addWidget(self.chk_hide_zeros)
        
        # Старые поля ввода маржи и демпинга удалены из разметки хедера хедера главного окна
        
        # Пружина отталкивает «Выделить все» в самый правый край
        row3_layout.addStretch()
        
        # Чекбокс массового выделения теперь стоит в конце строки хедера
        self.chk_select_all = QCheckBox("Выделить все")
        self.chk_select_all.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.chk_select_all.stateChanged.connect(self.toggle_all_table_checkboxes)
        row3_layout.addWidget(self.chk_select_all)
        # Небольшой зазор справа для идеального выравнивания по сетке
        row3_layout.addSpacing(10)
        
        # Собираем ряды по новому порядку (1 -> 2 -> 3)
        header_container_layout.addLayout(row1_layout)
        header_container_layout.addSpacing(5)
        header_container_layout.addLayout(row2_layout)
        header_container_layout.addSpacing(5)
        header_container_layout.addLayout(row3_layout)
        
        main_layout.addLayout(header_container_layout)

        # 🎯 ВСТРОЕННАЯ ПАНЕЛЬ ПОИСКА ДЛЯ CTRL+F (ИЗНАЧАЛЬНО СКРЫТА)
        self.search_panel = QWidget()
        search_panel_layout = QHBoxLayout(self.search_panel)
        search_panel_layout.setContentsMargins(5, 2, 5, 2)
        
        search_icon = QLabel("🔍 Найти на странице:")
        search_icon.setStyleSheet("font-weight: bold; color: #34495e;")
        search_panel_layout.addWidget(search_icon)
        
        self.search_field_input = QLineEdit()
        self.search_field_input.setPlaceholderText("Введите артикул или наименование для фильтрации строки...")
        self.search_field_input.setStyleSheet("padding: 4px; border: 1px solid #bdc3c7; border-radius: 3px;")
        # Подключаем мгновенную живую фильтрацию при изменении текста
        self.search_field_input.textChanged.connect(self.filter_main_table_rows)
        search_panel_layout.addWidget(self.search_field_input)
        
        btn_close_search = QPushButton("✕")
        btn_close_search.setToolTip("Закрыть панель поиска (Esc)")
        btn_close_search.setFixedWidth(25)
        btn_close_search.setStyleSheet("background-color: #95a5a6; color: white; border: none; font-weight: bold; border-radius: 3px;")
        btn_close_search.clicked.connect(self.hide_search_panel)
        search_panel_layout.addWidget(btn_close_search)
        
        self.search_panel.hide() # Скрываем панель при запуске программы
        main_layout.addWidget(self.search_panel)

        # --- ТАБЛИЦА ТОВАРОВ (Перестановка столбцов Цены конкурентов и Текущая розница) ---
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        # Устанавливаем заголовки с переносом строк (\n) для узких колонок
        self.table.setHorizontalHeaderLabels([
            "ID Woo", "Артикул", "Наименование\nтовара", 
            "Цена\nзакупки", "Цены\nконкурентов", "Текущая\nрозница", 
            "Расчетная\nцена", "Маржа", "%\nнаценки", "Ручная\nправка", "Выбор"
        ])
        
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        
        # Интеллектуальный адаптивный режим распределения ширины (занимает 100% окна)
        header = self.table.horizontalHeader()
        # 🎯 Переводим все 11 колонок в режим ручного изменения ширины мышкой (как в Excel)
        for col_idx in range(11):
            header.setSectionResizeMode(col_idx, QHeaderView.Interactive)
            
        # Задаем базовые стартовые размеры, чтобы при первом запуске таблица выглядела красиво
        self.table.setColumnWidth(0, 70)   # ID Woo
        self.table.setColumnWidth(1, 100)  # Артикул
        self.table.setColumnWidth(2, 350)  # Наименование
        self.table.setColumnWidth(3, 90)   # Цена закупки
        self.table.setColumnWidth(4, 220)  # Цены конкурентов (наша новая ширина)
        self.table.setColumnWidth(5, 110)  # Текущая розница
        self.table.setColumnWidth(6, 110)  # Расчетная цена
        self.table.setColumnWidth(7, 80)   # Маржа
        self.table.setColumnWidth(8, 80)   # % Наценки
        self.table.setColumnWidth(9, 100)  # Ручная правка
        self.table.setColumnWidth(10, 50)  # Выбор

        # Автоматически загружаем сохраненные пользователем размеры из реестра Windows
        from PySide6.QtCore import QSettings
        settings = QSettings("RepricerApp", "MainWindowSettings")
        saved_sizes = settings.value("TableColumnWidths")
        if saved_sizes and len(saved_sizes) == 11:
            for idx, width in enumerate(saved_sizes):
                try:
                    self.table.setColumnWidth(idx, int(width))
                except:
                    pass

        
        # Включаем аппаратное чередование цветов
        self.table.setAlternatingRowColors(True)
        
        # Принудительно переключаем стиль таблицы на профессиональный Fusion, 
        # который гарантированно прорисовывает зебру read-only ячеек на любых версиях Windows
        from PySide6.QtWidgets import QStyleFactory
        fusion_style = QStyleFactory.create("Fusion")
        if fusion_style:
            self.table.setStyle(fusion_style)
            
        # Задаем контрастный, но мягкий цвет для строк зебры
        self.table.setStyleSheet("""
            QTableWidget {
                alternate-background-color: #f1f3f5;
                background-color: #ffffff;
            }
        """)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemChanged.connect(self.handle_cell_changed)

        # 🎯 МГНОВЕННЫЙ ЗАПУСК СОПОСТАВЛЕНИЯ ПО ДВОЙНОМУ КЛИКУ МЫШИ
        self.table.itemDoubleClicked.connect(self.on_bind_competitor_clicked)
        
        # Перенаправляем HTMLDelegate на колонку 4 (Цены конкурентов)
        self.table.setItemDelegateForColumn(4, HTMLDelegate(self))
        
        main_layout.addWidget(self.table)

        # 🎯 ВНЕДРЕНИЕ ИНФОРМАЦИОННОГО ФУТЕРА С ЦВЕТОВОЙ ЛЕГЕНДОЙ СТРОК
        footer_panel = QWidget()
        footer_layout = QHBoxLayout(footer_panel)
        footer_layout.setContentsMargins(5, 5, 5, 5)
        
        lbl_legend_title = QLabel("<b>Цвета строк:</b>")
        lbl_legend_title.setStyleSheet("color: #34495e;")
        footer_layout.addWidget(lbl_legend_title)
        
        # Зеленый маркер
        lbl_green = QLabel("■ Связан с конкурентом")
        lbl_green.setStyleSheet("color: #27ae60; font-weight: bold; margin-left: 15px;")
        footer_layout.addWidget(lbl_green)
        
        # Желтый маркер
        lbl_yellow = QLabel("■ Включена минимальная маржа (демпинг опасен)")
        lbl_yellow.setStyleSheet("color: #d35400; font-weight: bold; margin-left: 15px;")
        footer_layout.addWidget(lbl_yellow)
        
        # Красный маркер
        lbl_red = QLabel("■ Нет цены закупки поставщика (товар отсутствует)")
        lbl_red.setStyleSheet("color: #c0392b; font-weight: bold; margin-left: 15px;")
        footer_layout.addWidget(lbl_red)

        # 🎯 ДОБАВЛЕНИЕ РАЗДЕЛИТЕЛЯ И НОВОЙ ЛЕГЕНДЫ ЦЕН КОНКУРЕНТОВ
        footer_layout.addSpacing(25)
        lbl_prices_title = QLabel("<b>Цвета цен конкурентов:</b>")
        lbl_prices_title.setStyleSheet("color: #34495e;")
        footer_layout.addWidget(lbl_prices_title)

        lbl_price_green = QLabel("■ Черный текст — В наличии")
        lbl_price_green.setStyleSheet("color: #2c3e50; font-weight: bold; margin-left: 15px;")
        footer_layout.addWidget(lbl_price_green)

        lbl_price_red = QLabel("■ Красный текст с (зак) / х — Под заказ / Нет в наличии")
        lbl_price_red.setStyleSheet("color: #e74c3c; font-weight: bold; margin-left: 15px;")
        footer_layout.addWidget(lbl_price_red)
        
        footer_layout.addStretch() # Прижимает всю легенду к левому краю футера
        main_layout.addWidget(footer_panel)

    def clear_main_table(self):
        """Слот для полной и принудительной очистки главной таблицы на экране"""
        self.table.blockSignals(True)
        self.table.clearContents()  # Намертво стирает текст во всех ячейках
        self.table.setRowCount(0)   # Удаляет сами строки с экрана
        self.table.blockSignals(False)
        print("[UI] Таблица принудительно очищена пользователем.")

    def show_user_manual(self):
        """Открывает встроенную интерактивную инструкцию по работе с репрайсером"""
        from PySide6.QtWidgets import QTextBrowser
        
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Руководство пользователя — Репрайсер WooCommerce")
        help_dialog.resize(800, 650)
        
        layout = QVBoxLayout(help_dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        
        browser = QTextBrowser()
        # Включаем поддержку внешних ссылок и копирования текста
        browser.setOpenExternalLinks(True)
        
        html_content = """
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #2c3e50; line-height: 1.6; padding: 10px;">
            
            <div style="background-color: #34495e; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                <h2 style="margin: 0; font-size: 20px;">🚀 РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ: РЕПРАЙСЕР WOOCOMMERCE</h2>
                <p style="margin: 5px 0 0 0; font-size: 13px; opacity: 0.9;">Система мониторинга конкурентов, аналитики маржи и автоматического ценообразования</p>
            </div>

            <p><b>Программа предназначена для</b> автоматического мониторинга цен конкурентов, расчета оптимальной стоимости собственных товаров на основе заложенных правил маржинальности и мгновенной синхронизации обновленных цен с вашим интернет-магазином на платформе WooCommerce. Система исключает человеческий фактор, защищает бизнес от торговли в убыток и позволяет удерживать лидерство на рынке за счет гибкого ценообразования.</p>

            <h3 style="color: #2980b9; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px;">ЧАСТЬ 1. ЧТО ТАКОЕ РЕПРАЙСИНГ И ЗАЧЕМ ОН НУЖЕН?</h3>
            <p><b>Репрайсинг (Repricing)</b> — это процесс изменения цен на товары в режиме реального времени в ответ на действия конкурентов, изменение закупочной стоимости или падение спроса.</p>
            <p>Если менеджер меняет цены вручную, он тратит дни на обход сайтов, совершает ошибки и не успевает за рынком. Программа делает это автоматически за секунды: она находит аналогичные товары на сайтах конкурентов, анализирует их актуальные цены/статусы и рассчитывает вашу новую цену так, чтобы вы оставались привлекательными для покупателей (демпинг), но не уходили ниже критического порога вашей прибыли (контроль маржи).</p>

            <h3 style="color: #2980b9; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px;">ЧАСТЬ 2. ГЛАВНОЕ ОКНО И СТРУКТУРА ТАБЛИЦЫ</h3>
            <p>Таблица на главном экране содержит 11 специализированных столбцов:</p>
            <ul>
                <li><b>ID Woo:</b> Уникальный цифровой код товара на вашем сайте. Нужен для точечной выгрузки. Не редактируется.</li>
                <li><b>Артикул:</b> Заводской код детали (SKU). Главный идентификатор для сквозной синхронизации между списками.</li>
                <li><b>Наименование товара:</b> Полное название позиции. По нему и артикулу работает живой фильтр (Ctrl + F).</li>
                <li><b>Цена закупки:</b> Стоимость, по которой вы приобретаете товар у поставщика. <b>Ячейка доступна для ручного изменения.</b></li>
                <li><b>Цены конкурентов:</b> Срез цен на рынке через разделитель |. Черный текст — в наличии. Красный текст с пометкой (зак) или х(зак) — под заказ (нет на складе). При выделении строки текст становится белым для читаемости.</li>
                <li><b>Текущая розница:</b> Действующая цена товара на вашем сайте в данный момент.</li>
                <li><b>Расчетная цена:</b> Идеальная цена, вычисленная математическим алгоритмом программы.</li>
                <li><b>Маржа:</b> Чистая прибыль в рублях (Расчетная цена минус Цена закупки).</li>
                <li><b>% Наценки:</b> Процент прибыли относительно закупки. Позволяет мгновенно оценить рентабельность позиции.</li>
                <li><b>Ручная правка:</b> Поле для экстренного вмешательства менеджера. <b>Доступно для ручного изменения.</b> Если ввести сюда число, программа отменит автоматические расчеты и жестко выставит эту цену как финальную.</li>
                <li><b>Выбор:</b> Нативные флажки (галочки) для массовой обработки товаров.</li>
            </ul>

            <h3 style="color: #2980b9; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px;">ЧАСТЬ 3. ЦВЕТОВАЯ ИНДИКАЦИЯ (ЛЕГЕНДА СИСТЕМЫ)</h3>
            <p>Программа использует умную цветовую разметку для мгновенной визуальной оценки состояния базы:</p>
            <p><b>Статусы строк (Товары):</b></p>
            <ul>
                <li><span style="background-color: #e0f8e0; padding: 2px 5px; border-radius: 3px; font-weight: bold; color: #1e7e34;">Светло-зелёный тон (Зебра):</span> Товар успешно связан с конкурентами. Система видит рынок и управляет ценой.</li>
                <li><span style="background-color: #f1f3f5; padding: 2px 5px; border-radius: 3px; font-weight: bold; color: #495057;">Белый / Серый (Зебра):</span> Стандартный товар. Связи с конкурентами пока не установлены.</li>
                <li><span style="background-color: #ffdc96; padding: 2px 5px; border-radius: 3px; font-weight: bold; color: #d35400;">Оранжевый фон:</span> Сработал триггер безопасности! Демпинговать дальше нельзя. Программа заблокировала падение цены и выставила её строго по вашей минимально допустимой марже.</li>
                <li><span style="background-color: #ffc8c8; padding: 2px 5px; border-radius: 3px; font-weight: bold; color: #c0392b;">Розовый/Красный фон:</span> У товара отсутствует цена закупки (равна 0.00). Расчетная цена автоматически приравнена к Текущей рознице во избежание ошибок.</li>
            </ul>
            <p><b>Статусы аналитики (Маржа и % Наценки):</b></p>
            <ul>
                <li><span style="color: #2ecc71; font-weight: bold;">Насыщенный зелёный (Наценка ≥ 40%):</span> Высокомаржинальный товар. Самые прибыльные позиции.</li>
                <li><span style="color: #27ae60;">Светло-зелёный (Наценка от 20% до 40%):</span> Средняя, стабильная маржинальность.</li>
            </ul>

            <h3 style="color: #2980b9; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px;">ЧАСТЬ 4. ПОШАГОВЫЙ АЛГОРИТМ РАБОТЫ (ИНСТРУКЦИЯ)</h3>
            <ol>
                <li><b>Авторизация:</b> При запуске введите ваш пароль (по умолчанию 1234). Без этого доступ к СУБД полностью заблокирован.</li>
                <li><b>Создание или импорт списка:</b> Выберите нужную категорию. При первом запуске нажмите «Импорт из WooCommerce», отметьте категории, оставьте флаг «только при количестве ≥ 1 шт.» и запустите импорт.</li>
                <li><b>Обновление закупок:</b> Нажмите «Обновить закупки». Программа в фоне соберет цены поставщиков из облака по артикулам.</li>
                <li><b>Связывание с конкурентами:</b> Если у товара нет связей, дважды кликните по строке товара. В открывшемся окне выберите точное совпадение и нажмите «Подтвердить связь». Старая связь не сотрется, пока вы не назначите новую карточку. <i>(Сбросить ошибочную связь можно через правый клик -> Сбросить привязку конкурентов, подтверждение отключено для скорости).</i></li>
                <li><b>Переобход конкурентов:</b> Нажмите «Запустить переобход конкурентов». Облачный скрипт обойдет сайты конкурентов и соберет их самые свежие цены на этот час. Вы увидите детальную статистику изменений.</li>
                <li><b>Запуск репрайсинга (Расчет цен):</b> Нажмите «Репрайсинг товаров». Откроется модальное окно параметров, которое запоминает ваши последние настройки (демпинг в наличии, демпинг под заказ с поддержкой знаков +/-, наценка без конкурентов, минимальная маржа). Система проверит заполнение полей и выполнит расчеты. Товары без закупки застрахуются автоматически!</li>
                <li><b>Массовые действия и синхронизация:</b> Отметьте нужные товары галочками (или нажмите «Выделить все» на панели). Выберите массовое действие: фильтрация на экране, экспорт прайс-листа в Excel (21 колонка для «GS Учёт») или выгрузка на сайт. Столбец «Текущая розница» обновится на экране мгновенно при пуше на сайт.</li>
            </ol>

            <h3 style="color: #2980b9; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px;">ЧАСТЬ 5. ГОРЯЧИЕ КЛАВИШИ И ЭРГОНОМИКА</h3>
            <ul>
                <li><b>Ctrl + C:</b> Мгновенное копирование значения любой выделенной ячейки в буфер обмена Windows.</li>
                <li><b>Правый клик по «Ручной правке»:</b> Меню «Вставить значение цены». Автоматически очищает текст от мусора, букв и пробелов, вставляет число и мгновенно пересчитывает показатели строки «на лету».</li>
                <li><b>Ctrl + F:</b> Открывает встроенную панель живого поиска. Введите часть артикула или названия для фильтрации.</li>
                <li><b>Esc:</b> Закрывает панель поиска и мгновенно возвращает видимость всех строк таблицы.</li>
                <li><b>Правый клик по комбобоксу списков:</b> Позволяет переименовать или полностью удалить текущую группу товаров по паролю.</li>
                <li><b>Кнопка «Задать пароль»:</b> Позволяет сменить текущий мастер-пароль для входа в приложение, запросив старый пароль для верификации.</li>
            </ul>
        </body>
        </html>
        """
        browser.setHtml(html_content)
        layout.addWidget(browser)
        
        # Кнопка закрытия
        btn_close = QPushButton("Понятно")
        btn_close.setStyleSheet("background-color: #34495e; color: white; font-weight: bold; padding: 6px;")
        btn_close.clicked.connect(help_dialog.accept)
        layout.addWidget(btn_close)
        
        help_dialog.exec()



    def on_create_new_list_clicked(self):
        """Слот для создания нового чистого списка товаров в базе данных"""
        from PySide6.QtWidgets import QInputDialog
        
        # Показываем красивое всплывающее поле ввода названия
        text, ok = QInputDialog.getText(
            self, 
            "Создание списка", 
            "Введите название для нового списка товаров:"
        )
        
        # Если пользователь ввел текст и нажал "ОК"
        if ok and text.strip():
            list_name = text.strip()
            
            conn = get_connection()
            cursor = conn.cursor()
            try:
                # Записываем новый список в таблицу product_lists
                cursor.execute(
                    "INSERT INTO product_lists (list_name) VALUES (?)", 
                    (list_name,)
                )
                conn.commit()
                print(f"[БД] Успешно создан новый список: '{list_name}'")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка БД", f"Не удалось создать список:\n{e}")
                return
            finally:
                conn.close()
                
            # Перечитываем комбобокс, чтобы в нем появился новый пункт
            self.refresh_lists_combobox()
            
            # Автоматически переключаем комбобокс на самый последний (только что созданный) пункт
            self.list_selector.setCurrentIndex(self.list_selector.count() - 1)

    # 🎯 ВОССТАНОВЛЕНИЕ ОРАНИЧЕНИЙ И КОНТЕКСТНОГО МЕНЮ УДАЛЕНИЯ СПИСКОВ
    def show_list_selector_context_menu(self, pos):
        """Создает контекстное меню по правому клику на комбобоксе списков"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        list_id = self.list_selector.currentData()
        list_name = self.list_selector.currentText()
        if list_id is None:
            return
            
        menu = QMenu(self)
        
        # 🎯 ДОБАВЛЕНО ДЕЙСТВИЕ ПЕРЕИМЕНОВАНИЯ СПИСКА СТРОГО ПО ТЗ
        action_rename = QAction(f"✏️ Переименовать список '{list_name}'", self)
        action_rename.triggered.connect(self.rename_selected_product_list)
        menu.addAction(action_rename)
        
        menu.addSeparator() # Аккуратный разделитель между пунктами
        
        action_delete = QAction(f"❌ Удалить список '{list_name}'", self)
        action_delete.triggered.connect(self.delete_selected_product_list)
        menu.addAction(action_delete)
        
        menu.exec(self.list_selector.mapToGlobal(pos))

    def rename_selected_product_list(self):
        """Метод безопасного изменения названия списка в СУБД и обновления UI"""
        from PySide6.QtWidgets import QInputDialog
        
        list_id = self.list_selector.currentData()
        list_name = self.list_selector.currentText()
        if list_id is None:
            return
            
        # Открываем диалоговое окно ввода текста, подставляя текущее имя списка
        text, ok = QInputDialog.getText(
            self, 
            "Переименование списка", 
            f"Введите новое название для списка '{list_name}':",
            text=list_name
        )
        
        # Если пользователь нажал ОК и ввёл не пустую строку
        if ok and text.strip():
            new_list_name = text.strip()
            
            # Если имя вообще не изменилось, просто выходим
            if new_list_name == list_name:
                return
                
            conn = get_connection()
            cursor = conn.cursor()
            try:
                # Обновляем имя списка в таблице product_lists
                cursor.execute(
                    "UPDATE product_lists SET list_name = ? WHERE id = ?", 
                    (new_list_name, list_id)
                )
                conn.commit()
                print(f"[БД Списки] Список ID {list_id} успешно переименован в '{new_list_name}'")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка БД", f"Не удалось переименовать список:\n{e}")
                return
            finally:
                conn.close()
                
            # Запоминаем ID текущего списка, чтобы после перезагрузки комбобокса не сбросился фокус
            current_saved_id = list_id
            
            # Перечитываем все списки из базы данных
            self.refresh_lists_combobox()
            
            # Находим обновленный список по его ID и программно выставляем на него фокус
            for index in range(self.list_selector.count()):
                if self.list_selector.itemData(index) == current_saved_id:
                    self.list_selector.setCurrentIndex(index)
                    break

    def delete_selected_product_list(self):
        """Метод защищенного удаления списка и всех его товаров по паролю"""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        
        list_id = self.list_selector.currentData()
        list_name = self.list_selector.currentText()
        if list_id is None:
            return
            
        # 1. Шаг проверки пароля администратора
        password, ok = QInputDialog.getText(
            self, 
            "Подтверждение удаления", 
            f"Внимание! Удаление списка '{list_name}' приведет к полной очистке всех входящих в него товаров и связей конкурентов.\n\nВведите пароль администратора для подтверждения:",
            QLineEdit.Password
        )
        
        if not ok:
            return # Отмена операции пользователем
            
        if password != "1234":
            QMessageBox.critical(self, "Доступ заблокирован", "Введен неверный пароль администратора! Удаление отменено.")
            return

        # 2. Шаг каскадного удаления из СУБД SQLite
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # Извлекаем ID всех товаров, привязанных к удаляемому списку
            cursor.execute("SELECT id FROM my_products WHERE list_id = ?", (list_id,))
            product_ids = [row[0] for row in cursor.fetchall()]
            
            if product_ids:
                # Превращаем массив в строку подстановок
                placeholders = ",".join("?" for _ in product_ids)
                # Очищаем накопленные розничные ссылки конкурентов для этих товаров
                cursor.execute(f"DELETE FROM competitor_links WHERE product_id IN ({placeholders})", product_ids)
                
            # Удаляем сами товары из списка
            cursor.execute("DELETE FROM my_products WHERE list_id = ?", (list_id,))
            # Удаляем запись о самом списке
            cursor.execute("DELETE FROM product_lists WHERE id = ?", (list_id,))
            
            conn.commit()
            print(f"[БД Списки] Полная каскадная очистка выполнена для списка ID: {list_id} ('{list_name}')")
            QMessageBox.information(self, "Успех", f"Список '{list_name}' и все связанные данные успешно удалены.")
            
        except Exception as e:
            print(f"[БД Списки] Критическая ошибка при удалении: {e}")
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось очистить список в базе данных:\n{e}")
        finally:
            conn.close()
            
        # Обновляем комбобокс и сбрасываем отображение
        self.refresh_lists_combobox()

    def refresh_lists_combobox(self):
        """Перечитывает все списки товаров из БД и принудительно инициализирует холодный старт"""
        self.list_selector.blockSignals(True)
        self.list_selector.clear()
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, list_name FROM product_lists")
        rows = cursor.fetchall()
        if not rows:
            cursor.execute("INSERT INTO product_lists (list_name) VALUES ('Основной список 1')")
            conn.commit()
            cursor.execute("SELECT id, list_name FROM product_lists")
            rows = cursor.fetchall()
            
        conn.close()

        for list_id, list_name in rows:
            self.list_selector.addItem(list_name, list_id)
            
        # Сначала разблокируем сигналы, чтобы комбобокс мог полноценно обновить связи
        self.list_selector.blockSignals(False)
        
        # 🎯 ХИРУРГИЧЕСКОЕ ФОРСИРОВАНИЕ: Намертво сбрасываем и повторно выставляем индекс 0.
        # Это аппаратно пинает внутренний движок Qt, заставляя его связать currentData с ID!
        if self.list_selector.count() > 0:
            self.list_selector.setCurrentIndex(-1)
            self.list_selector.setCurrentIndex(0)
        else:
            # Если списков вообще нет, вызываем загрузку вручную
            self.load_products_for_selected_list()

    def load_products_for_selected_list(self):
        from decimal import Decimal, ROUND_HALF_UP
        from PySide6.QtGui import QColor
        import time 
        
        list_id = self.list_selector.currentData()
        if list_id is None:
            return

        print("\n================== [ПАКЕТНАЯ ОПТИМИЗАЦИЯ START] ==================")
        t_start = time.perf_counter()

        # 1. ЗАМОРАЖИВАЕМ ИНТЕРФЕЙС И БЛОКИРУЕМ СИГНАЛЫ (Защита от бесконечного цикла)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        conn = None
        try:
            # Базовые значения для холодного старта отрисовки таблицы
            current_margin = 20.0
            current_dumping = 1.0

            t_db_start = time.perf_counter()
            conn = get_connection()
            cursor = conn.cursor()
            
            # Ускорение SQLite через оперативную память
            try:
                cursor.execute("PRAGMA journal_mode = WAL") 
                cursor.execute("PRAGMA synchronous = NORMAL") 
                cursor.execute("PRAGMA cache_size = -40000") 
            except: pass

            mapped_skus = set()
            try:
                cursor.execute("CREATE TABLE IF NOT EXISTS competitor_mappings (our_sku TEXT PRIMARY KEY, competitor_name TEXT, competitor_url TEXT)")
                cursor.execute("SELECT our_sku FROM competitor_mappings")
                # 🎯 ИСПРАВЛЕНИЕ ЦВЕТА: Извлекаем чистую строку row[0] вместо кортежа row
                mapped_skus = set(row[0] for row in cursor.fetchall() if row and row[0])
            except Exception as e:
                print(f"[ОПТИМИЗАЦИЯ] Ошибка competitor_mappings: {e}")

            # 1. ЗАПРОС ТОВАРОВ ТЕКУЩЕГО СПИСКА
            cursor.execute("""
                SELECT p.id, p.woo_id, p.sku, p.name, p.purchase_price, p.my_price, p.user_adjusted_price
                FROM my_products p
                WHERE p.list_id = ?
            """, (list_id,))
            base_products = cursor.fetchall()

            # 2. ОДИН ЗАЛПОВЫЙ ЗАПРОС ВСЕХ ЦЕН КОНКУРЕНТОВ И СТАТУСОВ ПО АРТИКУЛАМ (SKU) В ОЗУ
            try:
                cursor.execute("""
                    SELECT p.sku, cl.last_seen_price, cl.availability_status 
                    FROM competitor_links cl
                    JOIN my_products p ON p.id = cl.product_id
                    WHERE p.sku IS NOT NULL AND p.sku != ''
                """)
                all_prices_raw = cursor.fetchall()
            except Exception:
                cursor.execute("""
                    SELECT p.sku, cl.last_seen_price, 'в наличии'
                    FROM competitor_links cl
                    JOIN my_products p ON p.id = cl.product_id
                    WHERE p.sku IS NOT NULL AND p.sku != ''
                """)
                all_prices_raw = cursor.fetchall()
            
            # Строим глобальный кэш памяти по артикулу (SKU) товара
            prices_cache = {}
            for sku_code, price, status in all_prices_raw:
                clean_sku = str(sku_code).strip()
                if clean_sku not in prices_cache:
                    prices_cache[clean_sku] = []
                prices_cache[clean_sku].append({"price": price, "status": str(status).lower().strip()})

            self.lbl_last_update.setText("Дата последнего обновления Цен конкурентов: данные загружены в ОЗУ")
            self.lbl_last_update.setStyleSheet("font-weight: bold; color: #27ae60;")

            t_db_end = time.perf_counter()
            print(f"⏱ Шаг 1. ПАКЕТНАЯ работа с СУБД SQLite (все данные в ОЗУ): {(t_db_end - t_db_start):.4f} сек.")

            t_render_start = time.perf_counter()
            for row, prod in enumerate(base_products):
                self.table.insertRow(row)
                
                db_id          = prod[0]
                woo_id         = prod[1]
                sku            = prod[2]
                name           = prod[3]
                purchase_price = prod[4]
                current_retail = prod[5]
                user_adjusted  = prod[6]
                
                # Получаем связи конкурентов из кэша ОЗУ по артикулу товара для сквозного отображения
                clean_sku_key = str(sku).strip() if sku else ""
                comp_data_list = prices_cache.get(clean_sku_key, [])
                
                # Собираем только валидные цены "в наличии" для базового расчёта демпинга
                valid_in_stock_prices = []
                for item in comp_data_list:
                    p_val = item["price"]
                    p_status = item["status"]
                    if p_val is not None and p_val > 0:
                        if "под заказ" not in p_status and "нет в наличии" not in p_status:
                            valid_in_stock_prices.append(p_val)
                
                min_comp_price = min(valid_in_stock_prices) if valid_in_stock_prices else None
                
                is_no_purchase = False
                is_margin_safety_triggered = False
                
                # ФОРМИРУЕМ ИНДИВИДУАЛЬНО РАСКРАШЕННУЮ HTML-СТРОКУ ДЛЯ ДЕЛЕГАТА
                if comp_data_list:
                    html_parts = []
                    for item in comp_data_list:
                        p_val = item["price"]
                        p_status = item["status"]
                        
                        try:
                            clean_price_digits = "".join(c for c in str(p_val) if c.isdigit() or c in ".,").replace(",", ".")
                            float_price = float(clean_price_digits) if clean_price_digits else 0.0
                        except ValueError:
                            float_price = 0.0
                        
                        if float_price <= 0.01:
                            html_parts.append("<span style='color: #e74c3c; font-weight: bold;'>x(зак)</span>")
                        elif "под заказ" in p_status or "нет в наличии" in p_status:
                            html_parts.append(f"<span style='color: #e74c3c; font-weight: bold;'>{float_price:.2f}(зак)</span>")
                        else:
                            html_parts.append(f"<span style='color: #2c3e50;'>{float_price:.2f}</span>")
                            
                    competitor_cells_str = " | ".join(html_parts)
                else:
                    competitor_cells_str = "<span style='color: #7f8c8d; font-style: italic;'>Нет связей</span>"

                # Рассчитываем итоговую цену реализации
                if user_adjusted is not None and str(user_adjusted).strip() != "":
                    final_calculated_price = Decimal(str(user_adjusted))
                else:
                    if purchase_price and float(purchase_price) > 0:
                        safety_threshold = float(purchase_price) * (1 + current_margin / 100)
                        if min_comp_price is not None and float(min_comp_price) > 0:
                            dumped_price = float(min_comp_price) * (1 - current_dumping / 100)
                            if dumped_price >= safety_threshold:
                                final_calculated_price = Decimal(str(dumped_price))
                            else:
                                final_calculated_price = Decimal(str(safety_threshold))
                                is_margin_safety_triggered = True
                        else:
                            final_calculated_price = Decimal(str(current_retail if current_retail else 0))
                    else:
                        is_no_purchase = True
                        final_calculated_price = Decimal(str(current_retail if current_retail else 0))

                rounded_retail_str = f"{final_calculated_price.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.2f}"
                purchase_str = f"{float(purchase_price):.2f}" if purchase_price else "0.00"
                retail_str = f"{float(current_retail):.2f}" if current_retail else "0.00"

                # Вычисляем чистую маржу в рублях и процент наценки от закупки
                try:
                    p_float = float(purchase_price) if purchase_price else 0.0
                    calc_price_float = float(final_calculated_price)
                    
                    margin_rub = calc_price_float - p_float
                    margin_rub_str = f"{margin_rub:.2f}"
                    
                    if p_float > 0:
                        margin_percent = (margin_rub / p_float) * 100.0
                        margin_percent_str = f"{margin_percent:.1f}%"
                    else:
                        margin_percent = 0.0
                        margin_percent_str = "0.0%"
                except Exception:
                    margin_rub = 0.0
                    margin_percent = 0.0
                    margin_rub_str = "0.00"
                    margin_percent_str = "0.0%"

                # Формируем обновлённый массив из 10 полей (индексы от 0 до 9)
                fields = [
                    str(woo_id if woo_id is not None else ""),       
                    str(sku if sku is not None else ""),             
                    str(name if name is not None else ""),           
                    purchase_str,                                    
                    competitor_cells_str, 
                    retail_str,                             
                    rounded_retail_str,   
                    margin_rub_str,       # Индекс 7: Маржа в рублях
                    margin_percent_str,   # Индекс 8: % Наценки
                    str(user_adjusted if user_adjusted is not None else "") # Индекс 9: Ручная правка
                ]
                
                for col, val in enumerate(fields):
                    item = QTableWidgetItem(str(val))
                    if col in (0, 1, 2, 4, 5, 6, 7, 8):
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        
                    if col == 6 and is_no_purchase:
                        item.setBackground(QColor(255, 200, 200))
                    elif is_margin_safety_triggered:
                        item.setBackground(QColor(255, 220, 150))
                    elif sku in mapped_skus:
                        # Умная зебра для связанных товаров: чередуем тона зелёного цвета
                        if row % 2 == 1:
                            item.setBackground(QColor(220, 248, 220)) # Нежно-зелёный (светлый)
                        else:
                            item.setBackground(QColor(202, 242, 202)) # Чуть более насыщенный зелёный для объёма
                        
                    # Мягкая цветовая подсветка колонок Маржа и Наценка (индексы 7 и 8)
                    if not is_no_purchase and p_float > 0 and col in (7, 8):
                        if margin_percent >= 40.0:
                            item.setBackground(QColor(46, 204, 113, 50)) # Насыщенный зеленый
                        elif margin_percent >= 20.0:
                            item.setBackground(QColor(46, 204, 113, 20)) # Светло-зеленый
                        
                    if col == 0:
                        item.setData(Qt.UserRole, db_id)
                    self.table.setItem(row, col, item)
                    
                # Чекбокс массового выбора встает строго в 11-й столбец (индекс 10)
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk_item.setCheckState(Qt.Unchecked)
                self.table.setItem(row, 10, chk_item)
            print(f"⏱ Шаг 2. Мгновенная генерация ячеек из кэша ОЗУ: {(t_render_end - t_render_start):.4f} сек.")

        except Exception as table_err:
            print(f"[UI ТАБЛИЦА] КРИТ-ОШИБКА РЕНДЕРИНГА: {table_err}")
        finally:
            if conn:
                try: conn.close()
                except: pass
            
            t_filter_start = time.perf_counter()
            
            # Безопасное чтение чекбокса скрытия нулей при холодном старте
            check_state_val = 0
            if hasattr(self, 'chk_hide_zeros') and self.chk_hide_zeros is not None:
                try:
                    check_state_val = self.chk_hide_zeros.checkState().value
                except AttributeError:
                    check_state_val = int(self.chk_hide_zeros.checkState())
            
            self.filter_zero_purchase_rows(check_state_val)
            t_filter_end = time.perf_counter()
            
            # Восстанавливаем сигналы и включаем прорисовку ОДНИМ КАДРОМ
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True) 
            
            t_end = time.perf_counter()
            print(f"📈 ОБЩЕЕ ВРЕМЯ ВЫПОЛНЕНИЯ МЕТОДА: {(t_end - t_start):.4f} сек.")
            print("================== [ПАКЕТНАЯ ОПТИМИЗАЦИЯ END] ==================\n")

    def handle_cell_changed(self, item):
        """Обработчик ручного изменения ячеек в таблице товаров"""
        # 🎯 ВОССТАНОВЛЕНИЕ ПОТЕРЯННОЙ СТРОКИ: Теперь логика Qt работает безупречно!
        row = item.row()
        col = item.column()
        
        # 🎯 ИСПРАВЛЕНИЕ ИНДЕКСОВ: Реагируем строго на Цену закупки (3) и новую Ручную правку (9)
        if col not in (3, 9):
            return

        id_item = self.table.item(row, 0)
        if not id_item: 
            return
        product_id = id_item.data(Qt.UserRole)
        new_value = item.text().strip()
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            from decimal import Decimal, ROUND_HALF_UP
            
            # Получаем артикул текущего измененного товара для сквозного поиска копий
            sku_item = self.table.item(row, 1)
            sku_code = sku_item.text().strip() if sku_item else ""
            
            if col == 3:  # Цена закупки
                val = float(new_value) if new_value else 0.0
                if sku_code and sku_code != "Нет SKU":
                    cursor.execute("UPDATE my_products SET purchase_price = ? WHERE sku = ?", (val, sku_code))
                else:
                    cursor.execute("UPDATE my_products SET purchase_price = ? WHERE id = ?", (val, product_id))
                conn.commit()
                
            elif col == 9:  # Ручная правка
                val = float(new_value) if new_value else None
                if sku_code and sku_code != "Нет SKU":
                    cursor.execute("UPDATE my_products SET user_adjusted_price = ? WHERE sku = ?", (val, sku_code))
                else:
                    cursor.execute("UPDATE my_products SET user_adjusted_price = ? WHERE id = ?", (val, product_id))
                conn.commit()

            # 🎯 МГНОВЕННЫЙ ЛОКАЛЬНЫЙ ПЕРЕРАСЧЕТ СТРОКИ НА ЭКРАНЕ ПО НОВЫМ ИНДЕКСАМ
            self.table.blockSignals(True)
            
            # Извлекаем параметры репрайсинга по умолчанию (или последние сохраненные)
            try:
                current_margin = float(self.saved_min_margin.replace(',', '.'))
            except:
                current_margin = 20.0

            # Считываем актуальные данные по новым индексам: закупка (3), розница (5), ручная правка (9)
            p_item = self.table.item(row, 3)
            ret_item = self.table.item(row, 5) 
            adj_item = self.table.item(row, 9)
            
            p_val = float(p_item.text().strip()) if p_item and p_item.text().strip() else 0.0
            ret_val = float(ret_item.text().strip()) if ret_item and ret_item.text().strip() else 0.0
            adj_val = float(adj_item.text().strip()) if adj_item and adj_item.text().strip() else None
            
            # Определяем расчетную цену на основе приоритета ручной правки
            if adj_val is not None:
                final_calculated_price = Decimal(str(adj_val))
            else:
                if p_val > 0:
                    safety_threshold = p_val * (1 + current_margin / 100)
                    final_calculated_price = Decimal(str(safety_threshold))
                else:
                    final_calculated_price = Decimal(str(ret_val))

            # Округляем и записываем строго в Расчетную цену (колонка 6)
            rounded_retail_str = f"{final_calculated_price.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.2f}"
            calc_item = self.table.item(row, 6)
            if calc_item:
                calc_item.setText(rounded_retail_str)
                
                # Корректируем цвет расчетного поля при ручной правке (возвращаем стандартный белый/зебра)
                if p_val > 0:
                    calc_item.setBackground(QColor(255, 255, 255))

            # Автоматически пересчитываем новые столбцы Маржи (7) и % Наценки (8) для этой строки на экране
            try:
                calc_price_float = float(rounded_retail_str)
                margin_rub = calc_price_float - p_val
                
                margin_item = self.table.item(row, 7)
                percent_item = self.table.item(row, 8)
                
                if margin_item:
                    margin_item.setText(f"{margin_rub:.2f}")
                if percent_item:
                    if p_val > 0:
                        margin_percent = (margin_rub / p_val) * 100.0
                        percent_item.setText(f"{margin_percent:.1f}%")
                    else:
                        margin_percent = 0.0
                        percent_item.setText("0.0%")
                        
                # Обновляем цвет ячеек аналитики на лету в зависимости от маржинальности
                if p_val > 0 and margin_item and percent_item:
                    if margin_percent >= 40.0:
                        margin_item.setBackground(QColor(46, 204, 113, 50))
                        percent_item.setBackground(QColor(46, 204, 113, 50))
                    elif margin_percent >= 20.0:
                        margin_item.setBackground(QColor(46, 204, 113, 20))
                        percent_item.setBackground(QColor(46, 204, 113, 20))
                    else:
                        margin_item.setBackground(QColor(255, 255, 255))
                        percent_item.setBackground(QColor(255, 255, 255))
            except:
                pass
                
            self.table.blockSignals(False)
            
        except ValueError:
            self.table.blockSignals(True)
            QMessageBox.warning(self, "Ошибка ввода", "Пожалуйста, введите корректное число.")
            item.setText("")
            self.table.blockSignals(False)
        finally:
            conn.close()

    def toggle_all_table_checkboxes(self, state):
        """Слот массовой установки или снятия галочек со всех строк таблицы (Выбор в колонке 8)"""
        self.table.blockSignals(True)
        target_state = Qt.Checked if state == 2 else Qt.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 10) # Теперь чекбокс лежит в колонке 10
            if item:
                item.setCheckState(target_state)
        self.table.blockSignals(False)

    def filter_zero_purchase_rows(self, state):
        """Слот сверхбыстрой живой фильтрации: скрывает или показывает строки с ценой закупки 0.00"""
        # Превращаем состояние чекбокса в булев флаг
        should_hide_zeros = (state == 2 or state == Qt.Checked)
        
        self.table.setUpdatesEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                # Цена закупки лежит строго в классической колонке 3 (индекс 3)
                purchase_item = self.table.item(row, 3)
                
                if purchase_item:
                    try:
                        price_val = float(purchase_item.text().strip())
                    except ValueError:
                        price_val = 0.0
                        
                    # Если галочка стоит и закупка равна 0 — скрываем строку
                    if should_hide_zeros and price_val <= 0.0:
                        self.table.setRowHidden(row, True)
                    # Если галочку сняли и строка была скрыта именно из-за нуля — возвращаем её видимость
                    elif not should_hide_zeros:
                        self.table.setRowHidden(row, False)
        finally:
            self.table.setUpdatesEnabled(True)

    def execute_selected_bulk_action(self):
        """Диспетчер вызова массовых операций на базе нативных чекбоксов в колонке 8"""
        action_text = self.bulk_action_selector.currentText().strip()
        
        if action_text == "Показать весь список":
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
            
            self.bulk_action_selector.clear()
            self.bulk_action_selector.addItems([
                "работать с выделенными ячейками", "скрыть выделенные ячейки",
                "записать цены в woocommerce и в файл", "записать цены в файл"
            ])
            return

        checked_rows = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
                
            item = self.table.item(row, 10) # Считываем чекбокс из колонки 10
            if item and item.checkState() == Qt.Checked:
                checked_rows.append(row)

        if not checked_rows:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, отметьте галочками хотя бы один ВИДИМЫЙ товар в таблице!")
            return

        if action_text == "работать с выделенными ячейками":
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, row not in checked_rows)
            self._activate_show_all_menu_item()

        elif action_text == "скрыть выделенные ячейки":
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, row in checked_rows)
            self._activate_show_all_menu_item()
            
        elif action_text == "записать цены в файл":
            self._export_checked_rows_to_accounting_excel(checked_rows)

        elif action_text == "записать цены в woocommerce и в файл":
            file_success = self._export_checked_rows_to_accounting_excel(checked_rows, quiet=True)
            if file_success:
                self._push_checked_rows_to_woocommerce(checked_rows)

    def _activate_show_all_menu_item(self):
        """Вспомогательный метод переключения комбобоксов в режим отмены фильтрации"""
        self.bulk_action_selector.clear()
        self.bulk_action_selector.addItems(["Показать весь список"])

    def _export_checked_rows_to_accounting_excel(self, rows_list, quiet=False):
        """Генерирует оригинальный SpreadsheetML XLS-файл с пустыми графами по ТЗ без ошибок Windows"""
        from datetime import datetime
        import html
        
        # 🎯 ИСПРАВЛЕНИЕ: Считываем последний сохраненный путь экспорта из реестра Windows
        from PySide6.QtCore import QSettings
        settings = QSettings("RepricerApp", "MainWindowSettings")
        last_export_dir = settings.value("LastExportDirectory", "")

        path, _ = QFileDialog.getSaveFileName(
            self, 
            "Сохранить прайс-лист для GS Учёт", 
            last_export_dir, 
            "Книга Excel 97-2003 (*.xls)"
        )
        if not path:
            return False 

        # Сохраняем путь к выбранной папке для следующего раза
        import os
        settings.setValue("LastExportDirectory", os.path.dirname(path))
            
        try:
            # Плоские и чистые заголовки, строго в одну строку без \n
            headers = [
                "Наименование", "Артикул", "Штрих-код", "ед. измерения", "Масса упаковки",
                "Количество в упаковке", "ед. измерения упаковки", "Страна происхождения",
                "Цена импортера", "Код группы", "Валюта цены реализации", "Ставка НДС %",
                "Мин. остаток", "Код типа тмц", "Производитель", "Дата цен", "Оптовая цена",
                "Розничная цена", "Мелко-оптовая цена", "Дилерская цена", "Торговая марка"
            ]
            
            current_date_str = datetime.now().strftime("%d.%m.%Y")
            
            # Собираем валидный Microsoft Excel XML, который Excel и Windows считают родным оригиналом
            xml_data = '<?xml version="1.0" encoding="utf-8"?>\n'
            xml_data += '<?mso-application progid="Excel.Sheet"?>\n'
            xml_data += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
            xml_data += 'xmlns:o="urn:schemas-microsoft-com:office:office" '
            xml_data += 'xmlns:x="urn:schemas-microsoft-com:office:excel" '
            xml_data += 'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'
            xml_data += '  <Worksheet ss:Name="Цены для GS Учёт">\n'
            xml_data += '    <Table>\n'
            
            # 1. Запись хедера таблицы
            xml_data += '      <Row>\n'
            for h in headers:
                xml_data += f'        <Cell><Data ss:Type="String">{h}</Data></Cell>\n'
            xml_data += '      </Row>\n'
            
            # 2. Выгрузка товарных позиций
            for row in rows_list:
                sku_item = self.table.item(row, 1)
                name_item = self.table.item(row, 2)
                calc_item = self.table.item(row, 6)
                
                # Защита от спецсимволов (&, <, >, ") через нативный модуль html
                sku_val = html.escape(sku_item.text().strip()) if sku_item else ""
                name_val = html.escape(name_item.text().strip()) if name_item else ""
                calc_retail_price_str = calc_item.text().strip() if calc_item else "0.00"
                
                try: 
                    retail_price_float = float(calc_retail_price_str)
                except ValueError: 
                    retail_price_float = 0.0
                
                # 🎯 КАНОНИЧЕСКИЙ ВЫВОД СТРОГО ИЗ 21 КОЛОНКИ. Ненужные графы — абсолютно пустые теги Cell.
                xml_data += '      <Row>\n'
                xml_data += f'        <Cell><Data ss:Type="String">{name_val}</Data></Cell>\n'       # 1. Наименование
                xml_data += f'        <Cell><Data ss:Type="String">{sku_val}</Data></Cell>\n'        # 2. Артикул
                xml_data += '        <Cell></Cell>\n'                                               # 3. Штрих-код (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 4. ед. измерения (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 5. Масса упаковки (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 6. Количество в упаковке (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 7. ед. измерения упаковки (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 8. Страна происхождения (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 9. Цена импортера (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 10. Код группы (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 11. Валюта цены реализации (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 12. Ставка НДС % (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 13. Мин. остаток (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 14. Код типа тмц (ПУСТО)
                xml_data += '        <Cell></Cell>\n'                                               # 15. Производитель (ПУСТО)
                xml_data += f'        <Cell><Data ss:Type="String">{current_date_str}</Data></Cell>\n' # 16. Дата цен
                xml_data += '        <Cell><Data ss:Type="Number">0.00</Data></Cell>\n'             # 17. Оптовая цена
                xml_data += f'        <Cell><Data ss:Type="Number">{retail_price_float:.2f}</Data></Cell>\n' # 18. Розничная цена
                xml_data += '        <Cell><Data ss:Type="Number">0.00</Data></Cell>\n'             # 19. Мелко-оптовая цена
                xml_data += '        <Cell><Data ss:Type="Number">0.00</Data></Cell>\n'             # 20. Дилерская цена
                xml_data += '        <Cell></Cell>\n'                                               # 21. Торговая марка (ПУСТО)
                xml_data += '      </Row>\n'
                
            xml_data += '    </Table>\n'
            xml_data += '  </Worksheet>\n'
            xml_data += '</Workbook>\n'
            
            # Записываем как чистый валидный XML Excel-документ
            with open(path, mode='w', encoding='utf-8') as f:
                f.write(xml_data)
                
            if not quiet:
                QMessageBox.information(self, "Успех", f"Прайс-лист для 'GS Учёт' успешно создан!\nСохранено товаров: {len(rows_list)}")
            return True
            
        except Exception as e:
            print(f"[Экспорт XLS] Критическая ошибка: {e}")
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось сформировать прайс-лист:\n{e}")
            return False

    def _push_checked_rows_to_woocommerce(self, rows_list):
        """Метод массовой точечной отправки цен выделенных строк на боевой WooCommerce сайт"""
        import woocommerce_sync
        
        self.btn_apply_bulk.setEnabled(False)
        self.btn_apply_bulk.setText("⏳ Выгрузка...")
        QApplication.processEvents()
        
        pushed_count = 0
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            for row in rows_list:
                # ID Woo лежит в колонке 0 (индекс 0)
                id_item = self.table.item(row, 0)
                woo_id_str = id_item.text().strip() if id_item else ""
                # Расчетная цена лежит в колонке 6 (индекс 6)
                calculated_price_str = self.table.item(row, 6).text().strip()
                
                if woo_id_str and calculated_price_str:
                    try:
                        woo_id_int = int(woo_id_str)
                        price_float = float(calculated_price_str)
                        product_id = id_item.data(Qt.UserRole)
                        
                        # 1. Отправляем цену на боевой сайт WooCommerce
                        woocommerce_sync.update_single_product_price(woo_id_int, price_float)
                        pushed_count += 1
                        
                        # 2. Фиксируем новую цену розницы в локальной базе данных СУБД
                        cursor.execute("UPDATE my_products SET my_price = ? WHERE id = ?", (price_float, product_id))
                        conn.commit()
                        
                        # 3. Мгновенно обновляем Текущую розницу на экране (колонка 5)
                        self.table.blockSignals(True)
                        retail_item = self.table.item(row, 5)  # Индекс 5: Текущая розница
                        if retail_item:
                            retail_item.setText(f"{price_float:.2f}")
                        self.table.blockSignals(False)
                        
                    except ValueError:
                        continue # Пропускаем строки с битыми ID или ценами
            
            conn.close()
                    
            QMessageBox.information(self, "Успех синхронизации", f"Цены на сайте WooCommerce успешно обновлены!\nСинхронизировано товаров: {pushed_count}")

        except AttributeError:
            print("[UI Пакетный Пуш] Метод одиночного пуша отсутствует в модуле. Запуск общего перерасчета сайта...")
            try:
                woocommerce_sync.push_calculated_prices_to_website()
                QMessageBox.information(self, "Успех", "Массовая выгрузка цен на сайт завершена.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка выгрузки", f"Сбой отправки данных на сайт:\n{e}")
        except Exception as err:
            QMessageBox.critical(self, "Ошибка выгрузки", f"Сбой отправки данных на сайт:\n{err}")
        finally:
            self.btn_apply_bulk.setEnabled(True)
            self.bulk_action_selector.setCurrentIndex(0)
            self.btn_apply_bulk.setText("Применить")
            self.load_products_for_selected_list() # Мягко обновляем экран

    def open_import_dialog(self):
        list_id = self.list_selector.currentData()
        if list_id is None: 
            return
        dialog = ImportDialog(self, list_id)
        if dialog.exec() == QDialog.Accepted:
            self.load_products_for_selected_list()


    def open_excel_import_dialog(self):
        """Профессиональный метод импорта новых товаров из Excel/CSV файла напрямую в базу данных"""
        import csv
        
        # Получаем ID активного списка товаров, в котором мы находимся
        list_id = self.list_selector.currentData()
        if list_id is None:
            QMessageBox.warning(self, "Внимание", "Не выбран активный список товаров для загрузки!")
            return

        # 1. 🎯 ИСПРАВЛЕНИЕ: Считываем последний сохраненный путь импорта из реестра Windows
        from PySide6.QtCore import QSettings
        settings = QSettings("RepricerApp", "MainWindowSettings")
        last_import_dir = settings.value("LastImportDirectory", "")

        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Открыть файл импорта товаров (Excel CSV)", 
            last_import_dir, 
            "Файлы данных (*.csv *.txt)"
        )
        if not path:
            return # Отмена выбора файла

        # Сохраняем путь к выбранной папке для следующего раза
        import os
        settings.setValue("LastImportDirectory", os.path.dirname(path))

        # 2. Интеллектуальный подбор кодировки (защита от кракозябр MS Excel)
        encoding_to_try = 'utf-8'
        try:
            with open(path, mode='r', encoding='utf-8') as f:
                f.readline()
        except UnicodeDecodeError:
            encoding_to_try = 'windows-1251' # Если UTF-8 упал, значит это классический Windows Excel CSV

        # 3. Чтение файла и загрузка данных
        inserted_count = 0
        skipped_count = 0
        
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            with open(path, mode='r', encoding=encoding_to_try, errors='ignore') as f:
                # Автоматически определяем разделитель (запятая или точка с запятой)
                sample = f.read(2048)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample) if sample and ';' in sample or ',' in sample else None
                delimiter_char = dialect.delimiter if dialect else ';'
                
                reader = csv.reader(f, delimiter=delimiter_char)
                
                # Пропускаем первую строку (заголовок: Артикул;Наименование товара;Цена закупки)
                try:
                    next(reader)
                except StopIteration:
                    QMessageBox.warning(self, "Ошибка", "Выбранный файл абсолютно пустой!")
                    return

                # Переходим к пакетной транзакции SQLite для максимального ускорения записи
                cursor.execute("BEGIN TRANSACTION")
                
                for row_data in reader:
                    # Проверяем, что в строке есть хотя бы 2 колонки данных (Артикул и Название)
                    if len(row_data) < 2:
                        continue
                        
                    raw_sku = str(row_data[0]).strip()
                    raw_name = str(row_data[1]).strip()
                    
                    # Закупочная цена может быть необязательной, страхуем её
                    raw_price = str(row_data[2]).strip() if len(row_data) > 2 else "0.00"
                    
                    # Если нет артикула или названия — строку пропускаем
                    if not raw_sku or not raw_name:
                        skipped_count += 1
                        continue

                    # Профессиональная очистка цены от пробелов, букв 'руб.' и запятых
                    clean_price_digits = "".join(c for c in raw_price if c.isdigit() or c in ".,").replace(",", ".")
                    try:
                        purchase_price_float = float(clean_price_digits) if clean_price_digits else 0.0
                    except ValueError:
                        purchase_price_float = 0.0

                    # 4. Проверяем, существует ли уже такой товар ВНУТРИ ТЕКУЩЕГО СПИСКА
                    cursor.execute("""
                        SELECT id FROM my_products 
                        WHERE list_id = ? AND sku = ?
                    """, (list_id, raw_sku))
                    existing_product = cursor.fetchone()

                    if existing_product:
                        # Если товар найден — просто обновляем ему цену закупки и наименование
                        cursor.execute("""
                            UPDATE my_products 
                            SET name = ?, purchase_price = ? 
                            WHERE id = ?
                        """, (raw_name, purchase_price_float, int(existing_product[0])))
                    else:
                        # Если товара нет — создаем новую позицию. woo_id и my_price оставляем NULL
                        cursor.execute("""
                            INSERT INTO my_products (list_id, woo_id, sku, name, purchase_price, my_price)
                            VALUES (?, NULL, ?, ?, ?, 0.00)
                        """, (list_id, raw_sku, raw_name, purchase_price_float))
                        
                    inserted_count += 1

                conn.commit() # Надежно фиксируем транзакцию на диске
                
            print(f"[ИМПОРТ EXCEL] Успех. Загружено/обновлено: {inserted_count}, пропущено некорректных: {skipped_count}")
            QMessageBox.information(
                self, 
                "Импорт завершен", 
                f"Данные из файла успешно загружены в текущий список!\n\n"
                f"▪ Всего обработано позиций: {inserted_count}\n"
                f"▪ Пропущено строк без SKU/Имени: {skipped_count}"
            )
            
        except Exception as e:
            try: conn.rollback()
            except: pass
            print(f"[ИМПОРТ EXCEL] Критическая ошибка: {e}")
            QMessageBox.critical(self, "Ошибка импорта", f"Не удалось прочитать или записать файл:\n{e}")
        finally:
            conn.close()
            # Перерисовываем нашу таблицу на экране, чтобы сразу увидеть новые позиции!
            self.load_products_for_selected_list()

    def change_app_password_logic(self):
        """Метод изменения главного пароля системы с проверкой и двойным подтверждением"""
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pwd_hash FROM app_credentials WHERE id = 1")
        row = cursor.fetchone()
        current_db_pwd = row[0] if row else "1234"
        conn.close()
        
        # 1. Проверяем старый пароль
        old_pwd, ok1 = QInputDialog.getText(self, "Смена пароля", "Введите текущий пароль для подтверждения прав:", QLineEdit.Password)
        if not ok1: return
        if old_pwd != current_db_pwd:
            QMessageBox.critical(self, "Ошибка", "Старый пароль введён неверно! Изменение отменено.")
            return
            
        # 2. Запрашиваем новый пароль
        new_pwd, ok2 = QInputDialog.getText(self, "Смена пароля", "Введите НОВЫЙ пароль приложения:", QLineEdit.Password)
        if not ok2 or not new_pwd.strip():
            QMessageBox.warning(self, "Внимание", "Новый пароль не может быть пустым!")
            return
            
        # 3. Подтверждаем новый пароль перед вводом
        confirm_pwd, ok3 = QInputDialog.getText(self, "Смена пароля", "ПОВТОРИТЕ новый пароль для подтверждения:", QLineEdit.Password)
        if not ok3: return
        
        if new_pwd != confirm_pwd:
            QMessageBox.critical(self, "Ошибка", "Введённые новые пароли не совпадают! Изменение отменено.")
            return
            
        # 4. Сохраняем в СУБД SQLite
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE app_credentials SET pwd_hash = ? WHERE id = 1", (new_pwd.strip(),))
            conn.commit()
            QMessageBox.information(self, "Успех", "Главный пароль приложения успешно изменён и сохранён на диске!")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось сохранить новый пароль:\n{e}")
        finally:
            conn.close()

# НАЧАЛО ИЗМЕНЕНИЙ: main_window.py -> метод show_context_menu
    def show_context_menu(self, pos):
        """Динамически создает и отображает контекстное меню по правому клику мыши с поддержкой Clipboard"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction, QGuiApplication
        
        # Определяем, на какую конкретно ячейку нажал пользователь
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        selected_row = index.row()
        selected_col = index.column()
        
        # Принудительно делаем строку активной при правом клике
        self.table.setCurrentIndex(index)
        
        menu = QMenu(self)
        
        # 📋 ЛОГИКА КОПИРОВАНИЯ (Доступно для колонок Артикула, Наименования и Цен)
        if selected_col in (1, 2, 3, 4, 5, 6, 7, 8, 9):
            item = self.table.item(selected_row, selected_col)
            if item and item.text().strip():
                action_copy = QAction("📋 Скопировать значение", self)
                action_copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(item.text().strip()))
                menu.addAction(action_copy)
                menu.addSeparator()

        # 📥 ЛОГИКА ВСТАВКИ (Доступно строго для колонки 9 - Ручная правка)
        if selected_col == 9:
            clipboard_text = QGuiApplication.clipboard().text().strip()
            if clipboard_text:
                action_paste = QAction("📥 Вставить значение цены", self)
                action_paste.triggered.connect(lambda: self.paste_price_to_cell(selected_row, selected_col, clipboard_text))
                menu.addAction(action_paste)
                menu.addSeparator()
        
        # 🔗 Добавляем пункт мгновенного запуска сопоставления
        action_bind = QAction("🔗 Связать с конкурентами", self)
        action_bind.triggered.connect(self.on_bind_competitor_clicked)
        menu.addAction(action_bind)
        menu.addSeparator()
        
        # Действие 1: Сброс привязки (доступно всегда при клике на строку)
        action_reset = QAction("❌ Сбросить привязку конкурентов", self)
        action_reset.triggered.connect(self.delete_product_mapping)
        menu.addAction(action_reset)
        
        menu.exec(self.table.viewport().mapToGlobal(pos))
# КОНЕЦ ИЗМЕНЕНИЙ: main_window.py -> метод show_context_menu


    def paste_price_to_cell(self, row, col, text):
        """Вспомогательный метод безопасной вставки цены из буфера обмена"""
        # Извлекаем только цифры и разделители
        clean_text = "".join(c for c in text if c.isdigit() or c in ".,").replace(",", ".")
        if clean_text:
            item = self.table.item(row, col)
            if item:
                item.setText(clean_text) # Триггерит handle_cell_changed автоматически
            else:
                from PySide6.QtWidgets import QTableWidgetItem
                new_item = QTableWidgetItem(clean_text)
                self.table.setItem(row, col, new_item)

    def keyPressEvent(self, event):
        """Перехват системных горячих клавиш, таких как Ctrl+C для копирования ячеек"""
        from PySide6.QtGui import QKeySequence, QGuiApplication
        
        # Проверяем, нажал ли пользователь стандартную комбинацию Ctrl+C (или Cmd+C на Mac)
        if event.matches(QKeySequence.Copy):
            selected_indexes = self.table.selectedIndexes()
            if selected_indexes:
                # Берем индекс текущей выбранной ячейки
                current_index = self.table.currentIndex()
                if current_index.isValid():
                    col = current_index.column()
                    row = current_index.row()
                    # Разрешаем копировать Артикул, Имя и Любые цены
                    if col in (1, 2, 3, 4, 5, 6, 7, 8, 9):
                        item = self.table.item(row, col)
                        if item:
                            QGuiApplication.clipboard().setText(item.text().strip())
                            return
                            
        # 🎯 ПЕРЕХВАТ КОМБИНАЦИИ CTRL+F ДЛЯ ПОКАЗА ПАНЕЛИ ПОИСКА
        if event.matches(QKeySequence.Find):
            self.search_panel.show()
            self.search_field_input.setFocus() # Автоматически переводим курсор в поле ввода
            self.search_field_input.selectAll() # Выделяем старый текст для быстрой замены
            return
            
        # 🎯 ПЕРЕХВАТ КЛАВИШИ ESC ДЛЯ ЗАКРЫТИЯ ПОИСКА
        if event.key() == Qt.Key_Escape and self.search_panel.isVisible():
            self.hide_search_panel()
            return
                            
        super().keyPressEvent(event)

    def hide_search_panel(self):
        """Скрывает панель поиска и полностью сбрасывает фильтрацию таблицы"""
        self.search_field_input.clear()
        self.search_panel.hide()
        self.table.setFocus()
        # Гарантированно показываем обратно все строки таблицы
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)

    def filter_main_table_rows(self, text):
        """Живой поисковый движок: фильтрует строки со сверхбыстрой аппаратной оптимизацией"""
        search_query = text.strip().lower()
        
        # 🎯 ЗАМОРАЖИВАЕМ ОТРИСОВКУ: Отключаем Layout Recalculation на время цикла
        self.table.setUpdatesEnabled(False)
        
        try:
            # Если поле поиска пустое — мгновенно показываем все строки обратно
            if not search_query:
                for row in range(self.table.rowCount()):
                    self.table.setRowHidden(row, False)
                return

            # Сканируем каждую строчку на экране по исходным классическим индексам
            for row in range(self.table.rowCount()):
                sku_item = self.table.item(row, 1)  # Колонка 1: Артикул
                name_item = self.table.item(row, 2) # Колонка 2: Наименование товара
                
                sku_text = sku_item.text().lower() if sku_item else ""
                name_text = name_item.text().lower() if name_item else ""
                
                # Если поисковый запрос есть либо в артикуле, либо в названии позиций
                if search_query in sku_text or search_query in name_text:
                    self.table.setRowHidden(row, False) 
                else:
                    self.table.setRowHidden(row, True)  
        finally:
            # 🎯 РАЗМОРАЖИВАЕМ ОТРИСОВКУ: Принудительно обновляем экран ровно один раз
            self.table.setUpdatesEnabled(True)

    def delete_product_mapping(self):
        """Слот принудительного удаления связей выделенного товара с конкурентами"""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            return
            
        id_item = self.table.item(selected_row, 0)
        sku_item = self.table.item(selected_row, 1)
        
        if not id_item:
            return
            
        product_id = id_item.data(Qt.UserRole)
        sku_code = sku_item.text().strip() if sku_item else "Нет SKU"
        
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # 🎯 ИСПРАВЛЕНИЕ БАГА ЗАЛИПАНИЯ ЦЕН: Сквозная тотальная очистка и по ID, и по Артикулу (SKU)
            cursor.execute("BEGIN TRANSACTION")
            
            # 1. Сначала удаляем прямые связи по внутреннему ID текущей строки
            cursor.execute("DELETE FROM competitor_links WHERE product_id = ?", (product_id,))
            
            # 2. Если у товара есть живой артикул, каскадно вычищаем все цены конкурентов, 
            # привязанные к этому артикулу через таблицу my_products (это уберет скрытые дубли в СУБД)
            if sku_code and sku_code != "Нет SKU" and sku_code.strip() != "":
                cursor.execute("""
                    DELETE FROM competitor_links 
                    WHERE product_id IN (SELECT id FROM my_products WHERE sku = ?)
                """, (sku_code,))
                
                # 3. Полностью удаляем текстовый маркер мэтчинга площадок по артикулу
                cursor.execute("DELETE FROM competitor_mappings WHERE our_sku = ?", (sku_code,))
                
            conn.commit()
            print(f"[БД Связи] Тотальный сквозной сброс выполнен успешно. ID: {product_id}, SKU: {sku_code}")
            
        except Exception as e:
            print(f"[БД Связи] Ошибка при удалении связей: {e}")
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось очистить связи:\n{e}")
        finally:
            conn.close()
        
        # Перерисовываем интерфейс
        self.load_products_for_selected_list()

    def on_bind_competitor_clicked(self):
        """Слот инициализации параллельного многопоточного опроса площадок конкурентов"""
        from PySide6.QtWidgets import QProgressDialog
        
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, выделите товар в таблице для сопоставления!")
            return

        # 🎯 ЗАЩИТА РЕДАКТИРОВАНИЯ: Если кликнули по Закупке (3) или Ручной правке (9) — даем ввести цену руками
        current_col = self.table.currentColumn()
        if current_col in (3, 9):
            return
            
        sku_item = self.table.item(selected_row, 1)
        name_item = self.table.item(selected_row, 2)
        
        product_sku = sku_item.text().strip() if sku_item else "Нет SKU"
        product_name = name_item.text().strip() if name_item else "Нет названия"
        
        if product_sku == "Нет SKU" or not product_sku:
            QMessageBox.warning(self, "Ошибка", "У выбранного товара пустой артикул. Поиск невозможен!")
            return

        parsing_mode = self.parsing_mode_selector.currentText()
        
        # Сбрасываем контейнеры для сбора данных и потоков
        self.aggregated_data = {"ns_service": [], "rentall": [], "agrox": [], "onliner": [], "shop": []}
        self.active_threads = []
        self.active_workers = []
        self.completed_threads_count = 0
        self.expected_threads_count = 1
         
        # Информационное окно загрузки
        self.search_progress = QProgressDialog("Запуск фонового поиска цен...\nПожалуйста, подождите.", "Прервать", 0, 0, self)
        self.search_progress.setWindowTitle("Живой поиск цен")
        self.search_progress.setWindowModality(Qt.WindowModal)
        self.search_progress.setValue(0)
        self.search_progress.show()

        # 🎯 СВЯЗЫВАЕМ НАШ БЕЗОПАСНЫЙ СИГНАЛ С МЕТОДОМ ОТКРЫТИЯ ОКНА
        # Qt автоматически выполнит этот вызов в безопасном контексте главного UI-потока!
        self.all_search_threads_finished.connect(self.on_live_search_success_safe, Qt.QueuedConnection)

        if "садовая техника" in parsing_mode.lower():
            # 🔥 РЕЖИМ СУПЕР-СКОРОСТНОЙ ПАРАЛЛЕЛЛЬНОЙ РАБОТЫ (3 ПОТОКА ОДНОВРЕМЕННО)
            self.expected_threads_count = 3
            self.search_progress.setLabelText("Параллельный опрос площадок садовой техники:\nAgrox.by / Каталог Onliner / Shop.by...")
            print(f"\n[МНОГОПОТОЧНОСТЬ] Инициализация параллельного сбора. Цель: {product_sku}. Потоков: 3")
            
            # 1. Поток для Agrox.by
            from garden_worker import GardenSearchWorker
            th_ag = QThread()
            wk_ag = GardenSearchWorker(product_sku, product_name)
            wk_ag.moveToThread(th_ag)
            wk_ag.search_finished.connect(lambda data: self._handle_partial_search_success("agrox", data.get("rentall", [])))
            wk_ag.error_occurred.connect(lambda err: print(f"[Ошибка потока Agrox]: {err}"))
            self._bind_thread_lifecycle(th_ag, wk_ag)
            
            # 2. Поток для Onliner API
            from onliner_worker import OnlinerSearchWorker
            th_on = QThread()
            wk_on = OnlinerSearchWorker(product_sku, product_name)
            wk_on.moveToThread(th_on)
            wk_on.search_finished.connect(lambda data: self._handle_partial_search_success("onliner", data.get("rentall", [])))
            wk_on.error_occurred.connect(lambda err: print(f"[Ошибка потока Onliner]: {err}"))
            self._bind_thread_lifecycle(th_on, wk_on)
            
            # 3. Поток для Shop.by
            from shop_worker import ShopSearchWorker
            th_sh = QThread()
            wk_sh = ShopSearchWorker(product_sku, product_name)
            wk_sh.moveToThread(th_sh)
            wk_sh.search_finished.connect(lambda data: self._handle_partial_search_success("shop", data.get("rentall", [])))
            wk_sh.error_occurred.connect(lambda err: print(f"[Ошибка потока Shop.by]: {err}"))
            self._bind_thread_lifecycle(th_sh, wk_sh)
            
            # Одновременный залповый старт всех потоков
            th_ag.start()
            th_on.start()
            th_sh.start()
            
        else:
            # СТАНДАРТНЫЙ РЕЖИМ ДЛЯ ЗАПАСНЫХ ЧАСТЕЙ (1 ПОТОК)
            self.expected_threads_count = 1
            self.search_progress.setLabelText("Локальный поиск запчастей (Selenium)...\nПожалуйста, подождите.")
            
            from competitor_worker import LiveSearchWorker
            th_parts = QThread()
            wk_parts = LiveSearchWorker(product_sku, product_name)
            wk_parts.moveToThread(th_parts)
            
            # Для запчастей перенаправляем через тот же безопасный сигнал хендлера
            wk_parts.search_finished.connect(lambda data: self.all_search_threads_finished.emit(data))
            wk_parts.error_occurred.connect(self.on_live_search_error)
            self._bind_thread_lifecycle(th_parts, wk_parts)
            
            th_parts.start()

    def _bind_thread_lifecycle(self, thread, worker):
        """Вспомогательный метод для связывания жизненного цикла Qt потоков"""
        self.active_threads.append(thread)
        self.active_workers.append(worker)
        
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        self.search_progress.canceled.connect(thread.quit)

    def _handle_partial_search_success(self, site_key, results_list):
        """Слот-агрегатор частичных результатов из параллельных потоков садовой техники"""
        self.aggregated_data[site_key] = results_list
        self.completed_threads_count += 1
        
        print(f"[МНОГОПОТОЧНОСТЬ] Поток '{site_key}' завершен. Собрано позиций: {len(results_list)}. Успешность: {self.completed_threads_count}/{self.expected_threads_count}")
        
        # Если все три потока успешно завершили свою работу в фоне
        if self.completed_threads_count >= self.expected_threads_count:
            # 🎯 ВМЕСТО МЕДЛЕННОГО ВЫЗОВА UI ОТСЮДА, МЫ ВЫБРАСЫВАЕМ СИГНАЛ В ГЛАВНЫЙ ПОТОК
            self.all_search_threads_finished.emit(self.aggregated_data)

    def on_live_search_success_safe(self, data):
        """Безопасный многопоточный слот обработки успешного окончания сбора данных"""
        try: self.all_search_threads_finished.disconnect(self.on_live_search_success_safe)
        except: pass

        for th in self.active_threads:
            try: th.quit()
            except: pass
            
        if hasattr(self, 'search_progress') and self.search_progress:
            self.search_progress.close()
            self.search_progress = None
            
        selected_row = self.table.currentRow()
        if selected_row == -1: 
            self.active_threads.clear()
            self.active_workers.clear()
            return
        
        # 🎯 ЗАПОМИНАЕМ АКТИВНЫЙ ID ТОВАРА ПЕРЕД ПЕРЕРИСОВКОЙ ОКНА
        saved_woo_item = self.table.item(selected_row, 0)
        saved_woo_id = saved_woo_item.text().strip() if saved_woo_item else None
        
        product_id = self.table.item(selected_row, 0).data(Qt.UserRole)
        product_sku = self.table.item(selected_row, 1).text().strip()
        product_name = self.table.item(selected_row, 2).text().strip()
        
        # 🎯 ИСПРАВЛЕНИЕ: Считываем текущую закупку (индекс 3) и розницу (новый индекс 5) для аналитики
        purchase_val = self.table.item(selected_row, 3).text().strip() if self.table.item(selected_row, 3) else "0.00"
        retail_val   = self.table.item(selected_row, 5).text().strip() if self.table.item(selected_row, 5) else "0.00"
       
        # Передаем расширенный пакет данных в обновленный конструктор диалога
        dialog = CompetitorMappingDialog(
            product_sku=product_sku, 
            product_name=product_name, 
            purchase_price=purchase_val,
            current_retail=retail_val,
            search_results=data, 
            parent=self
        )
        
        if dialog.exec() == QDialog.Accepted:
            chosen_mappings = dialog.get_selected_mappings()
            if not chosen_mappings: 
                self.active_threads.clear()
                self.active_workers.clear()
                return
            
            conn = get_connection()
            cursor = conn.cursor()
            try:
                # 🎯 Динамически расширяем таблицу competitor_links полем статуса, если его нет
                try:
                    cursor.execute("ALTER TABLE competitor_links ADD COLUMN availability_status TEXT DEFAULT 'в наличии'")
                except:
                    pass # Колонка уже существует
                
                cursor.execute("BEGIN TRANSACTION")
                
                for result in chosen_mappings:
                    raw_price_str = str(result["price"]).strip()
                    
                    all_found_prices = re.findall(r'\d+(?:\.\d+)?', raw_price_str)
                    if all_found_prices:
                        clean_price = all_found_prices[0]
                    else:
                        clean_price = "".join(c for c in raw_price_str if c.isdigit() or c in ".,").replace(",", ".")
                    
                    price_val = float(clean_price) if clean_price else 0.0
                    
                    # Извлекаем статус из результата сопоставления (пока заглушка, далее на шагах 5 и 6 наполнится из парсеров)
                    status_val = result.get("status", "в наличии")
                    
                    cursor.execute("""
                        SELECT id FROM competitor_links 
                        WHERE product_id = ? AND competitor_url = ?
                    """, (product_id, result["url"]))
                    existing_row = cursor.fetchone()
                    
                    if existing_row:
                        # Извлекаем точный числовой ID из кортежа existing_row и обновляем цену и статус
                        cursor.execute("""
                            UPDATE competitor_links 
                            SET last_seen_price = ?, availability_status = ?, last_updated = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (price_val, status_val, int(existing_row[0])))
                    else:
                        cursor.execute("""
                            INSERT INTO competitor_links (product_id, competitor_url, last_seen_price, availability_status, last_updated)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (product_id, result["url"], price_val, status_val))
                        
                    cursor.execute("CREATE TABLE IF NOT EXISTS competitor_mappings (our_sku TEXT PRIMARY KEY, competitor_name TEXT, competitor_url TEXT)")
                    cursor.execute("""
                        INSERT OR REPLACE INTO competitor_mappings (our_sku, competitor_name, competitor_url)
                        VALUES (?, ?, ?)
                    """, (product_sku, result["competitor"], result["url"]))
                    
                    print(f"[БД Пакетная Связь] Буфер: {result['competitor']} -> {price_val} руб. ({status_val})")
                
                conn.commit()
                print("[БД Пакетная Связь] Успешно зафиксировано на диске за миллисекунды.")
            except Exception as db_err:
                try: conn.rollback()
                except: pass
                print(f"[БД Связи] Критическая ошибка пакетного сохранения: {db_err}")
            finally:
                conn.close()
                
            # Перерисовываем экран
            self.load_products_for_selected_list()
            
            # 🎯 ВОССТАНАВЛИВАЕМ МЕСТО РАБОТЫ И ФОКУС СТРОКИ МЕНЕДЖЕРА
            if saved_woo_id:
                for row_idx in range(self.table.rowCount()):
                    current_woo_item = self.table.item(row_idx, 0)
                    if current_woo_item and current_woo_item.text().strip() == saved_woo_id:
                        # Программно возвращаем синее выделение всей строки
                        self.table.setCurrentCell(row_idx, 0)
                        # Плавно скроллим таблицу Windows к этому элементу, если он ушел из видимости
                        self.table.scrollToItem(current_woo_item, QAbstractItemView.PositionAtCenter)
                        break
        else:
            print("\n[UI] Сопоставление отменено пользователем.")
            
        self.active_threads.clear()
        self.active_workers.clear()

    def on_live_search_error(self, error_message):
        """Вызывается автоматически, если фоновый поток упал с сетевой ошибкой"""
        if hasattr(self, 'search_progress') and self.search_progress:
            self.search_progress.close()
            
        QMessageBox.critical(
            self, 
            "Ошибка живого поиска", 
            f"Не удалось собрать данные с сайтов конкурентов:\n{error_message}"
        )

    # 🎯 ВЕТКА 1: ПОТОК СБОРА ЗАКУПОЧНЫХ ЦЕН ПОСТАВЩИКОВ
    @Slot()
    def start_purchases_thread(self):
        """Создает и запускает фоновый процесс сбора цен поставщиков для выбранного списка"""
        list_id = self.list_selector.currentData()
        if list_id is None:
            QMessageBox.warning(self, "Внимание", "Не выбран активный список товаров!")
            return

        print(f"\n[UI]: Инициализируем сбор закупок для списка ID {list_id}...")
        
        self.btn_update_purchases.setEnabled(False)
        self.btn_update_purchases.setText("⏳ Сбор закупок...")
        self.btn_start_repricing.setEnabled(False)
        self.table.setEnabled(False)

        self.reprice_thread = QThread()
        self.reprice_worker = RepriceWorker(mode="purchases", list_id=list_id)
        self.reprice_worker.moveToThread(self.reprice_thread)
        
        self.reprice_thread.started.connect(self.reprice_worker.run)
        self.reprice_worker.finished.connect(self.on_purchases_finished)
        self.reprice_worker.error_occurred.connect(self.on_purchases_error)

        self.reprice_worker.finished.connect(self.reprice_thread.quit)
        self.reprice_worker.error_occurred.connect(self.reprice_thread.quit)
        self.reprice_worker.finished.connect(self.reprice_worker.deleteLater)
        self.reprice_worker.error_occurred.connect(self.reprice_worker.deleteLater)
        self.reprice_thread.finished.connect(self.reprice_thread.deleteLater)

        self.reprice_thread.start()

    @Slot()
    def on_purchases_finished(self):
        """Обработка успешного окончания сбора закупочных цен"""
        self.btn_update_purchases.setEnabled(True)
        self.btn_update_purchases.setText("📥 Обновить закупки")
        self.btn_start_repricing.setEnabled(True)
        self.table.setEnabled(True)
        
        self.load_products_for_selected_list()
        QMessageBox.information(self, "Успех", "Закупочные цены поставщиков для выбранного списка успешно обновлены!")

    @Slot(str)
    def on_purchases_error(self, error_message):
        """Перехват исключений при сборе закупок"""
        self.btn_update_purchases.setEnabled(True)
        self.btn_update_purchases.setText("📥 Обновить закупки")
        self.btn_start_repricing.setEnabled(True)
        self.table.setEnabled(True)
        QMessageBox.critical(self, "Ошибка прайсов", f"Не удалось обновить закупки:\n{error_message}")


    # 🎯 ВЕТКА 2: ПОТОК МАССОВОГО РЕПРАЙСИНГА РОЗНИЦЫ И ВЫГРУЗКИ НА САЙТ
    @Slot()
    def start_repricing_thread(self):
        """Создает и запускает фоновый процесс массовой переоценки розницы конкурентов по выбранному списку"""
        
        # 🎯 ИСПРАВЛЕНИЕ: Берем ID активной группы напрямую из комбобокса фильтра групп на экране
        # Если ваш комбобокс называется иначе (например self.category_box), замените имя ниже
        if hasattr(self, 'group_combo'):
            list_id = self.group_combo.currentData()
        elif hasattr(self, 'category_box'):
            list_id = self.category_box.currentData()
        else:
            # Резервный вариант на случай, если используется старое имя
            list_id = self.list_selector.currentData()
            
        if list_id is None:
            QMessageBox.warning(self, "Внимание", "Не выбран активный список или группа товаров!")
            return

        print(f"\n[UI]: Инициализируем массовый репрайсинг для группы ID {list_id}...")
        
        self.btn_update_purchases.setEnabled(False)
        self.btn_start_repricing.setEnabled(False)
        self.btn_start_repricing.setText("⏳ Выполняется репрайсинг...")
        self.table.setEnabled(False)

        # 📋 Создаем информативное модальное окно ожидания с кнопкой отмены
        from PySide6.QtWidgets import QProgressDialog
        self.repricing_progress = QProgressDialog(
            "Выполняется массовый репрайсинг розницы через облачный скрипт...\n"
            "Облако обходит сайты конкурентов выбранной группы.\n\n"
            "Вы можете свернуть программу, процесс идет в фоновом режиме.", 
            "Прервать процесс", 0, 0, self
        )
        self.repricing_progress.setWindowTitle("Облачный репрайсинг")
        self.repricing_progress.setWindowModality(Qt.WindowModal)
        self.repricing_progress.setMinimumWidth(450)
        self.repricing_progress.show()

        self.reprice_thread = QThread()
        self.reprice_worker = RepriceWorker(mode="repricing", list_id=list_id)
        self.reprice_worker.moveToThread(self.reprice_thread)

        self.reprice_thread.started.connect(self.reprice_worker.run)
        self.reprice_worker.finished.connect(self.on_repricing_finished)
        self.reprice_worker.error_occurred.connect(self.on_repricing_error)

        # Привязываем закрытие окна ожидания и принудительное прерывание потока кнопкой "Прервать"
        self.reprice_worker.finished.connect(self.repricing_progress.close)
        self.reprice_worker.error_occurred.connect(self.repricing_progress.close)
        self.repricing_progress.canceled.connect(self.reprice_thread.quit)

        self.reprice_worker.finished.connect(self.reprice_thread.quit)
        self.reprice_worker.error_occurred.connect(self.on_repricing_error) # Страховка
        self.reprice_worker.finished.connect(self.reprice_worker.deleteLater)
        self.reprice_worker.error_occurred.connect(self.reprice_worker.deleteLater)
        self.reprice_thread.finished.connect(self.reprice_thread.deleteLater)

        self.reprice_thread.start()


    @Slot()
    def on_repricing_finished(self):
        """Обработка успешного окончания массового расчета розничных цен"""
        if hasattr(self, 'repricing_progress') and self.repricing_progress:
            self.repricing_progress.close()
            
        self.btn_update_purchases.setEnabled(True)
        self.btn_start_repricing.setEnabled(True)
        self.btn_start_repricing.setText("🚀 Запустить репрайсинг")
        self.table.setEnabled(True)
        
        # 🎯 ИСПРАВЛЕНИЕ ПУНКТА №7: Сохраняем старые розничные цены из таблицы в ОЗУ перед перерасчетом
        old_prices_snapshot = {}
        for row in range(self.table.rowCount()):
            sku_item = self.table.item(row, 1) # Колонка 1: Артикул
            retail_item = self.table.item(row, 5) # Колонка 5: Текущая розница
            if sku_item and retail_item:
                sku_str = sku_item.text().strip()
                try:
                    old_prices_snapshot[sku_str] = float(retail_item.text().strip())
                except ValueError:
                    old_prices_snapshot[sku_str] = 0.0

        # Принудительно загружаем новые данные из БД и выполняем свежий перерасчет на экране
        self.load_products_for_selected_list()
        
        # Считаем честную и точную статистику изменений по уже обновленной таблице
        changed_count = 0
        total_processed = self.table.rowCount()
        
        for row in range(total_processed):
            sku_item = self.table.item(row, 1)
            calculated_price_item = self.table.item(row, 6) # Колонка 6: Новая расчетная цена
            
            if sku_item and calculated_price_item:
                sku_str = sku_item.text().strip()
                if sku_str in old_prices_snapshot:
                    try:
                        old_price = old_prices_snapshot[sku_str]
                        new_price = float(calculated_price_item.text().strip())
                        # Фиксируем изменение, если цена сдвинулась хотя бы на 1 копейку
                        if abs(old_price - new_price) > 0.01:
                            changed_count += 1
                    except ValueError:
                        continue
        
        # Выводим красивое окно с детальной статистикой для менеджера
        stats_message = (
            f"Массовый репрайсинг розницы успешно завершен!\n\n"
            f"📊 Статистика обработки:\n"
            f"▪ Всего товаров в списке: {total_processed}\n"
            f"▪ Изменилась расчетная цена у {changed_count} позиций.\n\n"
            f"Данные обновлены в памяти программы. Вы можете выгрузить их в файл."
        )
        QMessageBox.information(self, "Успех репрайсинга", stats_message)

    @Slot(str)
    def on_repricing_error(self, error_message):
        """Перехват исключений при выполнении репрайсинга розницы с возможностью копирования лога"""
        if hasattr(self, 'repricing_progress') and self.repricing_progress:
            self.repricing_progress.close()
            
        self.btn_update_purchases.setEnabled(True)
        self.btn_start_repricing.setEnabled(True)
        self.btn_start_repricing.setText("🚀 Запустить репрайсинг")
        self.table.setEnabled(True)
        
        # Создаем продвинутое диалоговое окно ошибки
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Ошибка репрайсинга розницы")
        msg_box.setText("Произошла ошибка при связи с облаком или обработке данных.")
        
        # Добавляем скрываемую область с подробным текстовым логом, который можно выделить и скопировать (Ctrl+C)
        msg_box.setDetailedText(error_message)
        
        # Делаем так, чтобы текстовое поле с логом поддерживало стандартное выделение мышкой
        # В Qt подробный текст автоматически помещается в QTextEdit, который позволяет копировать информацию
        msg_box.exec()

    # 🎯 ВЕТКА 3: МАТЕМАТИЧЕСКИЙ МЕТОД ДЛЯ СПЕЦ-КНОПКИ РЕПРАЙСИНГА «ПОД ЗАКАЗ» С ПОДДЕРЖКОЙ ЗНАКОВ + И -
    @Slot()
    def start_order_repricing_logic(self):
        """Универсальный интеллектуальный репрайсинг товаров на основе введённых параметров"""
        list_id = self.list_selector.currentData()
        if list_id is None:
            QMessageBox.warning(self, "Внимание", "Не выбран активный список товаров!")
            return

        # 1. Открываем выпадающее модальное окно настроек
        dialog = RepriceSettingsDialog(self)
        if dialog.exec() != QDialog.Accepted:
            print("[UI Репрайсинг] Расчёт отменён пользователем.")
            return
            
        # Извлекаем проверенные и валидированные числа из формы настроек
        settings = dialog.results
        d_avail = settings["dumping_avail"]   # Демпинг от цен в наличии
        d_order = settings["dumping_order"]   # Демпинг от цен под заказ (+-)
        no_comp = settings["no_competitors"]  # Наценка при отсутствии конкурентов
        m_margin = settings["min_margin"]     # Контроль минимальной наценки

        print(f"\n[UI]: Запуск комплексного репрайсинга товаров для списка ID {list_id}...")
        
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        
        from decimal import Decimal, ROUND_HALF_UP
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            for row in range(self.table.rowCount()):
                id_item = self.table.item(row, 0)
                if not id_item:
                    continue
                product_id = id_item.data(Qt.UserRole)
                
                # Получаем цену закупки и текущую розницу прямо с экрана
                try:
                    purchase_val = float(self.table.item(row, 3).text())
                except:
                    purchase_val = 0.0
                    
                try:
                    retail_val = float(self.table.item(row, 5).text())
                except:
                    retail_val = 0.0

                # 🎯 ДОБАВЛЕНО: Безопасно считываем ручную правку (колонка 9) прямо с экрана перед расчетом
                try:
                    adj_item = self.table.item(row, 9)
                    adj_text = adj_item.text().strip() if adj_item else ""
                    if adj_text and adj_text.lower() != "none":
                        adj_val = float(adj_text.replace(',', '.'))
                    else:
                        adj_val = None
                except:
                    adj_val = None
                
                # 🎯 ИСПРАВЛЕНИЕ: Вытаскиваем артикул (SKU) строки, чтобы искать цены конкурентов так же, как экран
                sku_item = self.table.item(row, 1)
                sku_code = sku_item.text().strip() if sku_item else ""

                # Спрашиваем СУБД о ценах конкурентов по артикулу товара через связь с my_products
                cursor.execute("""
                    SELECT cl.last_seen_price, cl.availability_status 
                    FROM competitor_links cl
                    JOIN my_products p ON p.id = cl.product_id
                    WHERE p.sku = ? AND p.sku IS NOT NULL AND p.sku != ''
                """, (sku_code,))
                links = cursor.fetchall()
                
                # Порог безопасности (Контроль минимальной наценки %)
                safety_threshold = purchase_val * (1 + m_margin / 100)
                
                calculated_target = None
                is_safety_triggered = False
                is_no_comp_triggered = False
                is_order_logic_used = False
                is_manual_override_triggered = False

                # 🎯 ВЫСШИЙ ПРИОРИТЕТ: Если ручная правка присутствует, полностью блокируем перерасчёт
                if adj_val is not None:
                    calculated_target = adj_val
                    is_manual_override_triggered = True
                # Если ручной правки нет, запускаем стандартные правила репрайсинга
                elif purchase_val <= 0.0:
                    calculated_target = retail_val
                else:
                    if not links:
                        # Сценарий 1: Закупка есть, но цен конкурентов нет вообще
                        calculated_target = purchase_val * (1 + no_comp / 100)
                        is_no_comp_triggered = True
                    else:
                        # Разделяем конкурентов на категории
                        avail_prices = []
                        order_prices = []
                        
                        # Берём текстовое значение ячейки конкурентов прямо с экрана (колонка 4)
                        # Там уже гарантированно содержатся маркеры "(зак)" или "x(зак)" для товаров под заказ
                        comp_item_widget = self.table.item(row, 4)
                        screen_text = comp_item_widget.text().lower().strip() if comp_item_widget else ""
                        
                        for price, status in links:
                            if price is None or price <= 0:
                                continue
                            
                            # Переводим цену в текстовый формат, как она отображается в ячейке таблицы
                            price_str_format = f"{float(price):.2f}"
                            
                            # 🎯 НАДЁЖНАЯ ПРОВЕРКА: Если на экране рядом с этой ценой стоит маркер под заказ
                            if f"{price_str_format}(зак)" in screen_text or f"{price_str_format} (зак)" in screen_text or "x(зак)" in screen_text:
                                order_prices.append(price)
                            else:
                                # Если маркера под заказ на экране нет — цена относится к категории В НАЛИЧИИ
                                avail_prices.append(price)
                        
                        # Приоритет расчёта строго по условиям менеджера
                        if avail_prices:
                            # Сценарий 2: Главной является цена «в наличии» (знак + управляет направлением)
                            min_avail = min(avail_prices)
                            calculated_target = min_avail * (1 + d_avail / 100)
                        elif order_prices:
                            # Сценарий 3: Цен «в наличии» нет, считаем по «под заказ» (знак + исправлен)
                            min_order = min(order_prices)
                            calculated_target = min_order * (1 + d_order / 100)
                            is_order_logic_used = True
                        else:
                            calculated_target = purchase_val * (1 + no_comp / 100)
                            is_no_comp_triggered = True

                    # Жесткий контроль минимальной наценки (срабатывает только если закупка > 0 и это НЕ ручная правка)
                    if not is_manual_override_triggered and calculated_target < safety_threshold:
                        calculated_target = safety_threshold
                        is_safety_triggered = True

                final_price = Decimal(str(calculated_target))
                rounded_str = f"{final_price.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.2f}"
                
                # Мгновенно обновляем только Расчетную цену (колонка 6) на экране
                calc_item = self.table.item(row, 6)
                if calc_item:
                    calc_item.setText(rounded_str)
                    
                    # Цветовая индикация логики расчёта
                    if purchase_val <= 0:
                        calc_item.setBackground(QColor(255, 200, 200)) # Розовый (закупки нет)
                    elif is_safety_triggered:
                        calc_item.setBackground(QColor(255, 220, 150)) # Оранжевый (минимальная маржа)
                    elif is_no_comp_triggered:
                        calc_item.setBackground(QColor(174, 214, 241, 100)) # Синий (без конкурентов)
                    elif is_order_logic_used:
                        calc_item.setBackground(QColor(155, 89, 182, 40)) # Фиолетовый (логика под заказ)
                    else:
                        calc_item.setBackground(QColor(255, 255, 255))
                
                # Сохраняем результат автоматического репрайсинга в СУБД (my_price)
                cursor.execute("UPDATE my_products SET my_price = ? WHERE id = ?", (float(rounded_str), product_id))
                
                # Сразу же пересчитываем на экране аналитику Маржи и % Наценки для этой строки
                try:
                    c_float = float(rounded_str)
                    margin_rub = c_float - purchase_val
                    
                    margin_item = self.table.item(row, 7)
                    percent_item = self.table.item(row, 8)
                    
                    if margin_item:
                        margin_item.setText(f"{margin_rub:.2f}")
                    if percent_item:
                        if purchase_val > 0:
                            margin_percent = (margin_rub / purchase_val) * 100.0
                            percent_item.setText(f"{margin_percent:.1f}%")
                        else:
                            percent_item.setText("0.0%")
                except:
                    pass
                        
            conn.commit()
            print("[РЕПРАЙСИНГ] Всесторонний автоматический перерасчёт успешно сохранён в СУБД.")
            QMessageBox.information(self, "Успех", "Комплексный репрайсинг товаров успешно выполнен!\nРасчётные цены и аналитика обновлены.")
            
        except Exception as err:
            print(f"[ОШИБКА СПЕЦ-РЕПРАЙСИНГА]: {err}")
            QMessageBox.critical(self, "Ошибка расчёта", f"Не удалось выполнить переоценку:\n{err}")
        finally:
            conn.close()
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)


    def closeEvent(self, event):
        """Перехват закрытия окна: автоматически сохраняем ширину колонок в реестр Windows"""
        from PySide6.QtCore import QSettings
        try:
            settings = QSettings("RepricerApp", "MainWindowSettings")
            
            # Собираем текущую ширину всех 11 колонок таблицы
            current_widths = [self.table.columnWidth(i) for i in range(11)]
            settings.setValue("TableColumnWidths", current_widths)
            print("[СИСТЕМА] Размеры колонок успешно сохранены в настройки.")
        except Exception as e:
            print(f"[СИСТЕМА] Не удалось сохранить размеры колонок: {e}")
            
        super().closeEvent(event)

if __name__ == "__main__":
    import database
    print(f"\n[СИСТЕМА] База данных импортируется из файла: {database.__file__}\n")

    database.init_db()
    
    # Инициализация таблицы системного пароля авторизации для EXE
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS app_credentials (id INTEGER PRIMARY KEY, pwd_hash TEXT)")
        cursor.execute("SELECT pwd_hash FROM app_credentials WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO app_credentials (id, pwd_hash) VALUES (1, '1234')")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[СИСТЕМА] Ошибка инициализации таблицы паролей: {e}")

    # 🎯 СОЗДАНИЕ УСКОРЯЮЩИХ ИНДЕКСОВ ДЛЯ ЛИКВИДАЦИИ ТОРМОЗОВ ПРИ ПЕРЕКЛЮЧЕНИИ СПИСКОВ
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        # Индексируем привязку товаров к спискам категорий
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_list ON my_products(list_id)")
        # Индексируем связи розничных цен конкурентов с ID наших товаров
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_product ON competitor_links(product_id)")
        conn.commit()
        conn.close()
        print("[СИСТЕМА ИНДЕКСОВ] База данных успешно оптимизирована. Скорость повышена.")
    except Exception as idx_err:
        print(f"[СИСТЕМА ИНДЕКСОВ] Предупреждение оптимизации: {idx_err}")

    # Инициализируем ровно один главный системный экземпляр QApplication
    app = QApplication(sys.argv)
    
    # 🎯 БЕЗОПАСНАЯ ПРОВЕРКА АВТОРИЗАЦИИ ПЕРЕД ЗАПУСКОМ ГЛАВНОГО ОКНА
    login_dialog = LoginDialog()
    if login_dialog.exec() != QDialog.Accepted:
        sys.exit(0) # Мгновенный выход, если окно закрыли или нажали Выход
        
    window = MainWindow()
    
    # Запускаем окно сразу в полноценном развернутом режиме (на весь экран)
    window.showMaximized()
    
    # Принудительно пинаем прогрузку списков и товаров строго НА ОТКРЫТОМ ОКНЕ!
    window.refresh_lists_combobox()
    
    sys.exit(app.exec())


