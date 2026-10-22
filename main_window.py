import json
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QMessageBox, QCheckBox, 
                             QSlider, QComboBox, QFileDialog, QListWidget, QProgressBar)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from network.server_api import ServerAPI
from ui.settings_window import SettingsWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ServerAPI()
        self.selected_files = []  # Список путей к выбранным локальным файлам
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Загрузка товаров WooCommerce и ИИ-обработка")
        self.resize(850, 500)
        
        # === ЯКОРЬ НАЧАЛА: Создание верхнего меню настроек ===
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Опции")
        
        open_settings_action = QAction("Настройки системы", self)
        open_settings_action.triggered.connect(self.show_settings_window)
        settings_menu.addAction(open_settings_action)
        # === ЯКОРЬ КОНЦА: Создание верхнего меню настроек ===
        
        central = QWidget(self)
        self.setCentralWidget(central)
        
        # Главный горизонтальный макет для разделения на Левую и Правую панели
        main_layout = QHBoxLayout(central)
        
        # --- ЛЕВАЯ ПАНЕЛЬ: Параметры ИИ-конвейера ---
        ai_panel = QWidget()
        ai_layout = QVBoxLayout(ai_panel)
        ai_layout.setAlignment(Qt.AlignTop)
        ai_panel.setFixedWidth(260)
        
        ai_layout.addWidget(QLabel("<b>Параметры ИИ-обработки:</b>"))
        ai_layout.addSpacing(10)
        
        # 1. Настройка мягких теней
        self.shadow_cb = QCheckBox("Генерировать мягкие тени")
        self.shadow_cb.setChecked(True)
        ai_layout.addWidget(self.shadow_cb)
        ai_layout.addSpacing(15)
        
        # 2. Ползунок масштабирования объекта на холсте
        ai_layout.addWidget(QLabel("Масштаб товара на холсте:"))
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setMinimum(50)
        self.scale_slider.setMaximum(100)
        self.scale_slider.setValue(85)
        self.scale_lbl = QLabel("85%")
        self.scale_slider.valueChanged.connect(lambda v: self.scale_lbl.setText(f"{v}%"))
        
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.scale_slider)
        slider_layout.addWidget(self.scale_lbl)
        ai_layout.addLayout(slider_layout)
        ai_layout.addSpacing(15)
        
        # 3. Выбор позиции водяного знака магазина zatarka.by
        ai_layout.addWidget(QLabel("Позиция водяного знака:"))
        self.watermark_combo = QComboBox()
        self.watermark_combo.addItem("Справа внизу", "bottom_right")
        self.watermark_combo.addItem("Слева внизу", "bottom_left")
        self.watermark_combo.addItem("Справа вверху", "top_right")
        self.watermark_combo.addItem("Слева вверху", "top_left")
        self.watermark_combo.addItem("По центру", "center")
        ai_layout.addWidget(self.watermark_combo)
        ai_layout.addSpacing(30)
        
        # Кнопка запуска пакета фото в сеть
        self.btn_process_ai = QPushButton("Запустить ИИ-обработку пачки")
        self.btn_process_ai.setStyleSheet("background-color: #2b78e4; color: white; font-weight: bold; height: 32px;")
        self.btn_process_ai.clicked.connect(self.handle_process_batch)
        ai_layout.addWidget(self.btn_process_ai)
        
        # --- ПРАВАЯ ПАНЕЛЬ: Загрузка товаров и Очередь файлов ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Старый блок работы с товарами сайта
        self.products_label = QLabel("Нажмите кнопку, чтобы загрузить товары с сайта...", self)
        self.products_label.setWordWrap(True)
        right_layout.addWidget(self.products_label)
        
        self.btn_load = QPushButton("Получить 5 товаров с zatarka.by", self)
        self.btn_load.clicked.connect(self.handle_load_products)
        right_layout.addWidget(self.btn_load)
        right_layout.addSpacing(20)
        
        # Новый блок пакетной очереди изображений
        right_layout.addWidget(QLabel("<b>Очередь изображений для обработки:</b>"))
        
        btn_files_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("Добавить фото товаров")
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_clear_queue = QPushButton("Очистить очередь")
        self.btn_clear_queue.clicked.connect(self._on_clear_queue)
        btn_files_layout.addWidget(self.btn_add_files)
        btn_files_layout.addWidget(self.btn_clear_queue)
        right_layout.addLayout(btn_files_layout)
        
        self.file_list_widget = QListWidget()
        right_layout.addWidget(self.file_list_widget)
        
        # Элементы индикации прогресса
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ожидание выбора файлов...")
        right_layout.addWidget(self.status_label)
        
        # Добавляем панели в главный макет
        main_layout.addWidget(ai_panel)
        main_layout.addWidget(right_panel)

    # === ЯКОРЬ НАЧАЛА: Логика вызова и обработки окна настроек ===
    def show_settings_window(self):
        """Создает и отображает модальное окно настроек"""
        self.settings_win = SettingsWindow(self)
        # Подписываемся на сигнал изменения настроек/языка для будущих обновлений UI
        self.settings_win.settings_changed.connect(self.handle_settings_updated)
        self.settings_win.exec()

    def handle_settings_updated(self):
        """Вызывается автоматически, когда пользователь нажимает 'Сохранить' в настройках"""
        # На следующих шагах здесь будет перезапуск инициализации языковых констант главного окна
        pass
    # === ЯКОРЬ КОНЦА: Логика вызова и обработки окна настроек ===

    def handle_load_products(self):
        self.products_label.setText("Подключение к серверу и скачивание товаров...")
        
        # Запрашиваем товары у нашего сервера
        products = self.api.fetch_products()
        
        if products:
            result_text = "<b>Первые 5 товаров с сайта:</b><br><br>"
            for p in products:
                result_text += f"📦 ID: {p['id']} | <b>{p['name']}</b> — {p['price']} руб.<br>"
            self.products_label.setText(result_text)
        else:
            self.products_label.setText("<span style='color: red;'>Сервер вернул пустой список. Проверьте черное окно сервера!</span>")

    # --- Новая логика управления локальной пакетной очередью ---
    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите фото товаров поставщика", "", "Images (*.jpg *.jpeg *.png)"
        )
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self.file_list_widget.addItem(os.path.basename(f))
            self.status_label.setText(f"Файлов в очереди: {len(self.selected_files)}")

    def _on_clear_queue(self):
        self.selected_files.clear()
        self.file_list_widget.clear()
        self.progress_bar.setVisible(False)
        self.status_label.setText("Очередь очищена.")

    def handle_process_batch(self):
        if not self.selected_files:
            QMessageBox.warning(self, "Внимание", "Очередь пуста! Сначала добавьте изображения товаров.")
            return

        # Блокируем управляющие кнопки интерфейса
        self.btn_process_ai.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_clear_queue.setEnabled(False)
        
        self.progress_bar.setMaximum(len(self.selected_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Формируем словарь параметров из GUI
        params = {
            'shadow': self.shadow_cb.isChecked(),
            'scale': self.scale_slider.value() / 100.0,
            'watermark_pos': self.watermark_combo.currentData()
        }

        # Отправляем задачу в асинхронный многопоточный метод шлюза
        self.api.process_batch_images(
            file_paths=self.selected_files,
            params=params,
            on_progress=self._on_worker_progress,
            on_success=self._on_worker_success,
            on_failed=self._on_worker_failed,
            on_finish=self._on_worker_finished
        )

    # --- Колбэки-обработчики сигналов из фонового сетевого потока ---
    def _on_worker_progress(self, index, filename):
        self.progress_bar.setValue(index)
        self.status_label.setText(f"Отправка ({index}/{len(self.selected_files)}): {filename}")

    def _on_worker_success(self, filename, content_bytes):
        # Автоматически создаем папку результатов на Рабочем столе пользователя
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Zatarka_Ready")
        os.makedirs(output_dir, exist_ok=True)
        
        # Сохраняем обработанную ИИ-карточку в формате PNG
        name_part, _ = os.path.splitext(filename)
        out_path = os.path.join(output_dir, f"ready_{name_part}.png")
        with open(out_path, 'wb') as f:
            f.write(content_bytes)

    def _on_worker_failed(self, filename, error_message):
        print(f"[ИИ Конвейер] Сбой обработки файла {filename}: {error_message}")

    def _on_worker_finished(self):
        # Возвращаем элементы интерфейса в активное состояние
        self.btn_process_ai.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.btn_clear_queue.setEnabled(True)
        self.status_label.setText("Пакетная ИИ-обработка завершена!")
