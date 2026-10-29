import json
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QMessageBox, QCheckBox, 
                             QSlider, QComboBox, QFileDialog, QTableWidget, 
                             QTableWidgetItem, QProgressBar, QHeaderView)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from network.server_api import ServerAPI
from ui.settings_window import SettingsWindow
from utils.localization import LocalizationManager, _

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ServerAPI()
        self.selected_files = []  
        
        self.loc_manager = LocalizationManager()
        self.loc_manager.language_changed.connect(self.retranslate_ui)
        
        self.init_ui()

    def init_ui(self):
        self.resize(900, 550)
        
        menubar = self.menuBar()
        self.settings_menu = menubar.addMenu("")
        
        self.open_settings_action = QAction("", self)
        self.open_settings_action.triggered.connect(self.show_settings_window)
        self.settings_menu.addAction(self.open_settings_action)
        
        central = QWidget(self)
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        
        # --- ЛЕВАЯ ПАНЕЛЬ: Параметры ИИ-конвейера ---
        ai_panel = QWidget()
        ai_layout = QVBoxLayout(ai_panel)
        ai_layout.setAlignment(Qt.AlignTop)
        ai_panel.setFixedWidth(260)
        
        self.lbl_ai_header = QLabel()
        ai_layout.addWidget(self.lbl_ai_header)
        ai_layout.addSpacing(10)
        
        self.shadow_cb = QCheckBox()
        self.shadow_cb.setChecked(True)
        ai_layout.addWidget(self.shadow_cb)
        ai_layout.addSpacing(15)
        
        self.lbl_scale_title = QLabel()
        ai_layout.addWidget(self.lbl_scale_title)
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
        
        self.lbl_watermark_title = QLabel()
        ai_layout.addWidget(self.lbl_watermark_title)
        self.watermark_combo = QComboBox()
        ai_layout.addWidget(self.watermark_combo)
        ai_layout.addSpacing(30)
        
        self.btn_process_ai = QPushButton()
        self.btn_process_ai.setStyleSheet("background-color: #2b78e4; color: white; font-weight: bold; height: 32px;")
        self.btn_process_ai.clicked.connect(self.handle_process_batch)
        ai_layout.addWidget(self.btn_process_ai)
        
        # --- ПРАВАЯ ПАНЕЛЬ: Загрузка товаров и Таблица очереди ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        self.products_label = QLabel()
        self.products_label.setWordWrap(True)
        right_layout.addWidget(self.products_label)
        
        self.btn_load = QPushButton(self)
        self.btn_load.clicked.connect(self.handle_load_products)
        right_layout.addWidget(self.btn_load)
        right_layout.addSpacing(20)
        
        self.lbl_queue_header = QLabel()
        right_layout.addWidget(self.lbl_queue_header)
        
        btn_files_layout = QHBoxLayout()
        self.btn_add_files = QPushButton()
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_clear_queue = QPushButton()
        self.btn_clear_queue.clicked.connect(self._on_clear_queue)
        btn_files_layout.addWidget(self.btn_add_files)
        btn_files_layout.addWidget(self.btn_clear_queue)
        right_layout.addLayout(btn_files_layout)
        
        # Перевод очереди на QTableWidget для многоколоночного трекинга автомата
        self.task_table = QTableWidget(0, 3)
        self.task_table.setHorizontalHeaderLabels(["", "", ""])
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.task_table)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel()
        right_layout.addWidget(self.status_label)
        
        main_layout.addWidget(ai_panel)
        main_layout.addWidget(right_panel)

        self.retranslate_ui()

    def retranslate_ui(self):
        """Динамический перевод и обновление всех надписей 'на лету'"""
        self.setWindowTitle(_('window_title'))
        self.settings_menu.setTitle(_('menu_options'))
        self.open_settings_action.setText(_('settings_title'))
        
        self.lbl_ai_header.setText(f"<b>{_('lbl_ai_params')}</b>")
        self.shadow_cb.setText(_('chk_drop_shadow'))
        self.lbl_scale_title.setText(_('lbl_canvas_scale'))
        self.lbl_watermark_title.setText(_('lbl_watermark_pos'))
        self.btn_process_ai.setText(_('btn_process_ai'))
        
        if not self.selected_files:
            self.status_label.setText(_('status_waiting'))
        
        if "📦" not in self.products_label.text() and "span" not in self.products_label.text():
            self.products_label.setText(_('lbl_load_products_init'))
            
        self.btn_load.setText(_('btn_load_products'))
        self.lbl_queue_header.setText(f"<b>{_('lbl_queue_title')}</b>")
        self.btn_add_files.setText(_('btn_add_files'))
        self.btn_clear_queue.setText(_('btn_clear_queue'))

        # Динамическое обновление заголовков таблицы i18n
        self.task_table.setHorizontalHeaderLabels([
            _('col_filename'), _('col_status'), _('col_actions')
        ])

        # Синхронный перевод текущих статусов в таблице при смене языка
        for row in range(self.task_table.rowCount()):
            status_item = self.task_table.item(row, 1)
            if status_item:
                sys_status = status_item.data(Qt.UserRole)
                if sys_status:
                    status_item.setText(_(f"state_{sys_status.lower()}"))

        current_idx = self.watermark_combo.currentIndex()
        if current_idx == -1: current_idx = 0
            
        self.watermark_combo.clear()
        self.watermark_combo.addItem(_('watermark_bottom_right'), "bottom_right")
        self.watermark_combo.addItem(_('watermark_bottom_left'), "bottom_left")
        self.watermark_combo.addItem(_('watermark_top_right'), "top_right")
        self.watermark_combo.addItem(_('watermark_top_left'), "top_left")
        self.watermark_combo.addItem(_('watermark_center'), "center")
        self.watermark_combo.setCurrentIndex(current_idx)
    def show_settings_window(self):
        self.settings_win = SettingsWindow(self)
        self.settings_win.exec()

    def handle_load_products(self):
        self.products_label.setText(_('msg_loading_products'))
        products = self.api.fetch_products()
        if products:
            result_text = _('msg_products_header')
            for p in products:
                result_text += f"📦 ID: {p['id']} | <b>{p['name']}</b> — {p['price']} руб.<br>"
            self.products_label.setText(result_text)
        else:
            self.products_label.setText(_('msg_server_error'))

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, _('btn_add_files'), "", "Images (*.jpg *.jpeg *.png)"
        )
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    row = self.task_table.rowCount()
                    self.task_table.insertRow(row)
                    
                    filename = os.path.basename(f)
                    self.task_table.setItem(row, 0, QTableWidgetItem(filename))
                    
                    init_status = QTableWidgetItem(_('state_pending'))
                    init_status.setData(Qt.UserRole, "PENDING")
                    self.task_table.setItem(row, 1, init_status)
                    self.task_table.setItem(row, 2, QTableWidgetItem("0%"))
                    
            self.status_label.setText(f"{_('btn_add_files')}: {len(self.selected_files)}")

    def _on_clear_queue(self):
        self.selected_files.clear()
        self.task_table.setRowCount(0)
        self.progress_bar.setVisible(False)
        self.status_label.setText(_('status_cleared'))

    def handle_process_batch(self):
        if not self.selected_files:
            QMessageBox.warning(self, _('msg_empty_queue_title'), _('msg_empty_queue_body'))
            return

        self.btn_process_ai.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_clear_queue.setEnabled(False)
        
        self.progress_bar.setMaximum(len(self.selected_files))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        params = {
            'shadow': self.shadow_cb.isChecked(),
            'scale': self.scale_slider.value() / 100.0,
            'watermark_pos': self.watermark_combo.currentData()
        }

        self.api.process_batch_images(
            file_paths=self.selected_files,
            params=params,
            on_progress=self._on_worker_progress,
            on_status_change=self._on_worker_status_change,
            on_success=self._on_worker_success,
            on_failed=self._on_worker_failed,
            on_finish=self._on_worker_finished
        )

    def _on_worker_progress(self, index, filename):
        self.progress_bar.setValue(index)
        msg = _('status_sending').format(index=index, total=len(self.selected_files), filename=filename)
        self.status_label.setText(msg)

    def _on_worker_status_change(self, filename, system_status):
        """Интеграция с Конечным Автоматом: обновление статуса строки в реальном времени"""
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.text() == filename:
                status_item = self.task_table.item(row, 1)
                if status_item:
                    status_item.setText(_(f"state_{system_status.lower()}"))
                    status_item.setData(Qt.UserRole, system_status)
                
                # Маппинг прогресса для пользователя на UI
                progress_item = self.task_table.item(row, 2)
                if progress_item:
                    mapping = {"PENDING": "10%", "DOWNLOADING": "30%", "PROCESSING": "60%", "UPLOADING": "90%", "SUCCESS": "100%", "FAILED": "❌"}
                    progress_item.setText(mapping.get(system_status, "0%"))
                break

    def _on_worker_success(self, filename, content_bytes):
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Zatarka_Ready")
        os.makedirs(output_dir, exist_ok=True)
        
        name_part, _ = os.path.splitext(filename)
        out_path = os.path.join(output_dir, f"ready_{name_part}.png")
        with open(out_path, 'wb') as f:
            f.write(content_bytes)

    def _on_worker_failed(self, filename, error_message):
        self._on_worker_status_change(filename, "FAILED")
        print(f"[ИИ Конвейер] Сбой обработки файла {filename}: {error_message}")

    def _on_worker_finished(self):
        self.btn_process_ai.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.btn_clear_queue.setEnabled(True)
        self.status_label.setText(_('status_finished'))
