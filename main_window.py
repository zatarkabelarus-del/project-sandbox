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
        self.resize(1000, 640)
        
        menubar = self.menuBar()
        self.settings_menu = menubar.addMenu("")
        
        self.open_settings_action = QAction("", self)
        self.open_settings_action.triggered.connect(self.show_settings_window)
        self.settings_menu.addAction(self.open_settings_action)
        
        central = QWidget(self)
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        
        # --- ЛЕВАЯ ПАНЕЛЬ: Параметры ИИ-конвейера и Стилизации ---
        ai_panel = QWidget()
        ai_layout = QVBoxLayout(ai_panel)
        ai_layout.setAlignment(Qt.AlignTop)
        ai_panel.setFixedWidth(300)
        
        self.lbl_ai_header = QLabel()
        ai_layout.addWidget(self.lbl_ai_header)
        ai_layout.addSpacing(10)
        
        # Выбор контекста платформы
        self.lbl_site_context = QLabel("<b>Целевая e-commerce платформа:</b>")
        ai_layout.addWidget(self.lbl_site_context)
        self.site_combo = QComboBox()
        self.site_combo.addItem("zatarka.by", "zatarka.by")
        self.site_combo.addItem("Универсальный шаблон", "default")
        ai_layout.addWidget(self.site_combo)
        ai_layout.addSpacing(15)
        
        self.shadow_cb = QCheckBox()
        self.shadow_cb.setChecked(True)
        ai_layout.addWidget(self.shadow_cb)
        
        # Адаптивные слайдеры тени
        self.lbl_blur_title = QLabel("Радиус мягкого размытия:")
        ai_layout.addWidget(self.lbl_blur_title)
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(1, 50)
        self.blur_slider.setValue(15)
        self.blur_lbl = QLabel("15px")
        self.blur_slider.valueChanged.connect(lambda v: self.blur_lbl.setText(f"{v}px"))
        
        blur_layout = QHBoxLayout()
        blur_layout.addWidget(self.blur_slider)
        blur_layout.addWidget(self.blur_lbl)
        ai_layout.addLayout(blur_layout)
        
        self.lbl_opacity_title = QLabel("Плотность/Прозрачность тени:")
        ai_layout.addWidget(self.lbl_opacity_title)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 90)
        self.opacity_slider.setValue(35)
        self.opacity_lbl = QLabel("35%")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v}%"))
        
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_lbl)
        ai_layout.addLayout(opacity_layout)
        ai_layout.addSpacing(15)
        
        # Масштаб холста
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
        ai_layout.addSpacing(25)
        
        self.btn_process_ai = QPushButton()
        self.btn_process_ai.setStyleSheet("background-color: #2b78e4; color: white; font-weight: bold; height: 32px;")
        self.btn_process_ai.clicked.connect(self.handle_process_batch)
        ai_layout.addWidget(self.btn_process_ai)
        
        ai_layout.addSpacing(15)
        self.btn_test_local = QPushButton()
        self.btn_test_local.setStyleSheet("background-color: #34a853; color: white; font-weight: bold; height: 28px;")
        self.btn_test_local.clicked.connect(self._on_add_files)
        ai_layout.addWidget(self.btn_test_local)
        # --- ПРАВАЯ ПАНЕЛЬ: Очередь таблиц ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        self.products_label = QLabel()
        self.products_label.setWordWrap(True)
        right_layout.addWidget(self.products_label)
        
        self.btn_load = QPushButton(self)
        self.btn_load.clicked.connect(self.handle_load_excel_price_list)
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
        
        self.task_table = QTableWidget(0, 3)
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
        self.setWindowTitle(_('window_title'))
        self.settings_menu.setTitle(_('menu_options'))
        self.open_settings_action.setText(_('settings_title'))
        
        self.lbl_ai_header.setText(f"<b>{_('lbl_ai_params')}</b>")
        self.shadow_cb.setText(_('chk_drop_shadow'))
        self.lbl_scale_title.setText(_('lbl_canvas_scale'))
        self.lbl_watermark_title.setText(_('lbl_watermark_pos'))
        self.btn_process_ai.setText(_('btn_process_ai'))
        self.btn_test_local.setText(_('btn_test_local_features'))
        
        if not self.selected_files:
            self.status_label.setText(_('status_waiting'))
        if "📦" not in self.products_label.text() and "span" not in self.products_label.text():
            self.products_label.setText(_('lbl_load_products_init'))
            
        self.btn_load.setText(_('btn_load_excel_price'))
        self.lbl_queue_header.setText(f"<b>{_('lbl_queue_title')}</b>")
        self.btn_add_files.setText(_('btn_add_files'))
        self.btn_clear_queue.setText(_('btn_clear_queue'))

        self.task_table.setHorizontalHeaderLabels([
            _('col_filename'), _('col_status'), _('col_actions')
        ])

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

    def handle_load_excel_price_list(self):
        file_path, file_filter = QFileDialog.getOpenFileName(self, _('btn_load_excel_price'), "", "Excel Files (*.xlsx *.xls);;CSV Files (*.csv)")
        if not file_path: return

        self.products_label.setText(_('msg_loading_products'))
        parsed_report = self.api.import_excel_catalog(file_path)
        
        if parsed_report and parsed_report.get("status") == "success":
            success_count = parsed_report.get("success_count", 0)
            failed_rows = parsed_report.get("failed_rows", {})
            
            result_text = f"<b>{_('msg_import_complete')}</b><br>Успешно добавлено товаров: {success_count}<br>"
            self.products_label.setText(result_text)
            
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle(_('title_import_report'))
            
            report_body = f"Успешно обработано позиций: {success_count}\n"
            if failed_rows:
                report_body += f"\nВнимание! Пропущено строк ({len(failed_rows)}):\n"
                for row_num, reason in failed_rows.items():
                    report_body += f"• Строка {row_num}: {reason}\n"
            msg_box.setText(report_body)
            msg_box.exec()
            
            if "items" in parsed_report:
                for item in parsed_report["items"]:
                    self._add_item_to_table(item["filename"], source_type="REMOTE")
        else:
            self.products_label.setText(_('msg_server_error'))

    def _add_item_to_table(self, filename_or_path, source_type="LOCAL"):
        filename = os.path.basename(filename_or_path)
        for row in range(self.task_table.rowCount()):
            existing_item = self.task_table.item(row, 0)
            if existing_item and existing_item.text() == filename: return

        row = self.task_table.rowCount()
        self.task_table.insertRow(row)
        self.task_table.setItem(row, 0, QTableWidgetItem(filename))
        
        init_status = QTableWidgetItem(_('state_pending'))
        init_status.setData(Qt.UserRole, "PENDING")
        self.task_table.setItem(row, 1, init_status)
        
        progress_item = QTableWidgetItem("0%")
        progress_item.setData(Qt.UserRole, source_type)
        self.task_table.setItem(row, 2, progress_item)

    def _on_add_files(self):
        files, file_filter = QFileDialog.getOpenFileNames(self, _('btn_add_files'), "", "Images (*.jpg *.jpeg *.png)")
        if files:
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self._add_item_to_table(f, source_type="LOCAL")
            self.status_label.setText(f"{_('btn_add_files')}: {len(self.selected_files)}")

    def _on_clear_queue(self):
        self.selected_files.clear()
        self.task_table.setRowCount(0)
        self.progress_bar.setVisible(False)
        self.status_label.setText(_('status_cleared'))

    def handle_process_batch(self):
        if not self.selected_files and self.task_table.rowCount() == 0:
            QMessageBox.warning(self, _('msg_empty_queue_title'), _('msg_empty_queue_body'))
            return

        self.btn_process_ai.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_clear_queue.setEnabled(False)
        
        self.progress_bar.setMaximum(self.task_table.rowCount())
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        style_config = {
            "site_context": self.site_combo.currentData(),
            "shadow": {
                "offset_x": 12,
                "offset_y": 18,
                "blur_radius": self.blur_slider.value(),
                "shadow_opacity": self.opacity_slider.value() / 100.0
            }
        }

        params = {
            'shadow': self.shadow_cb.isChecked(),
            'scale': self.scale_slider.value() / 100.0,
            'watermark_pos': self.watermark_combo.currentData(),
            'style_config': style_config
        }

        self.api.process_batch_images(
            file_paths=self.selected_files, params=params,
            on_progress=self._on_worker_progress, on_status_change=self._on_worker_status_change,
            on_success=self._on_worker_success, on_failed=self._on_worker_failed, on_finish=self._on_worker_finished
        )

    def _on_worker_progress(self, index, filename):
        self.progress_bar.setValue(index)
        self.status_label.setText(_('status_sending').format(index=index, total=self.task_table.rowCount(), filename=filename))

    def _on_worker_status_change(self, filename, system_status):
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.text() == filename:
                status_item = self.task_table.item(row, 1)
                if status_item:
                    status_item.setText(_(f"state_{system_status.lower()}"))
                    status_item.setData(Qt.UserRole, system_status)
                
                progress_item = self.task_table.item(row, 2)
                if progress_item:
                    mapping = {"PENDING": "10%", "DOWNLOADING": "30%", "PROCESSING": "60%", "UPLOADING": "90%", "SUCCESS": "100%", "FAILED": "❌"}
                    progress_item.setText(mapping.get(system_status, "0%"))
                break

    def _on_worker_success(self, filename, content_bytes):
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Zatarka_Ready")
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"ready_{filename}")
        with open(out_path, 'wb') as f: f.write(content_bytes)

    def _on_worker_failed(self, filename, error_message):
        self._on_worker_status_change(filename, "FAILED")

    def _on_worker_finished(self):
        self.btn_process_ai.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.btn_clear_queue.setEnabled(True)
        self.status_label.setText(_('status_finished'))
