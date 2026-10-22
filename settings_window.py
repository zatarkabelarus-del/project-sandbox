import os
import json
import configparser
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QComboBox, QPushButton, QGroupBox, QFormLayout)
from PySide6.QtCore import Qt, Signal

class SettingsWindow(QDialog):
    # Сигнал для уведомления главного окна о смене языка или настроек
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
        self.config = configparser.ConfigParser()
        self.load_config()
        
        self.current_lang = self.config.get('General', 'language', fallback='ru')
        self.translations = self.load_translations(self.current_lang)
        
        self.init_ui()

    def load_config(self):
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding='utf-8')
        else:
            self.config['General'] = {'language': 'ru'}
            self.config['API'] = {
                'server_url': 'http://127.0.0.1:8000',
                'woo_client_id': '',
                'woo_client_secret': ''
            }
            self.save_config_file()

    def save_config_file(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def load_translations(self, lang):
        locale_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales', f'{lang}.json')
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def init_ui(self):
        self.resize(450, 300)
        self.main_layout = QVBoxLayout(self)

        # === Группа API ===
        self.api_group = QGroupBox()
        self.api_form = QFormLayout(self.api_group)
        
        self.lbl_server = QLabel()
        self.txt_server = QLineEdit(self.config.get('API', 'server_url', fallback=''))
        self.api_form.addRow(self.lbl_server, self.txt_server)
        
        self.lbl_woo_id = QLabel()
        self.txt_woo_id = QLineEdit(self.config.get('API', 'woo_client_id', fallback=''))
        self.api_form.addRow(self.lbl_woo_id, self.txt_woo_id)
        
        self.lbl_woo_secret = QLabel()
        self.txt_woo_secret = QLineEdit(self.config.get('API', 'woo_client_secret', fallback=''))
        self.txt_woo_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_form.addRow(self.lbl_woo_secret, self.txt_woo_secret)
        
        self.main_layout.addWidget(self.api_group)

        # === Группа Интерфейса ===
        self.ui_group = QGroupBox()
        self.ui_form = QFormLayout(self.ui_group)
        
        self.lbl_lang = QLabel()
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(['RU', 'EN'])
        self.combo_lang.setCurrentText(self.current_lang.upper())
        self.combo_lang.currentTextChanged.connect(self.change_language)
        self.ui_form.addRow(self.lbl_lang, self.combo_lang)
        
        self.main_layout.addWidget(self.ui_group)

        # === Кнопки управления ===
        self.btn_layout = QHBoxLayout()
        self.btn_save = QPushButton()
        self.btn_cancel = QPushButton()
        
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_save)
        self.btn_layout.addWidget(self.btn_cancel)
        self.main_layout.addLayout(self.btn_layout)

        self.retranslate_ui()

    def retranslate_ui(self):
        """Динамическое обновление текстовых констант во всех виджетах"""
        t = self.translations
        self.setWindowTitle(t.get('settings_title', 'Settings'))
        self.api_group.setTitle(t.get('api_section', 'API'))
        self.lbl_server.setText(t.get('server_url', 'Server URL:'))
        self.lbl_woo_id.setText(t.get('woo_client_id', 'Client ID:'))
        self.lbl_woo_secret.setText(t.get('woo_client_secret', 'Client Secret:'))
        self.ui_group.setTitle(t.get('interface_section', 'Interface'))
        self.lbl_lang.setText(t.get('language_label', 'Language:'))
        self.btn_save.setText(t.get('btn_save', 'Save'))
        self.btn_cancel.setText(t.get('btn_cancel', 'Cancel'))

    def change_language(self, text):
        lang = text.lower()
        if lang != self.current_lang:
            self.current_lang = lang
            self.translations = self.load_translations(lang)
            self.retranslate_ui()

    def save_settings(self):
        # Перенос из UI в объект конфигурации
        self.config['General']['language'] = self.current_lang
        self.config['API']['server_url'] = self.txt_server.text().strip()
        self.config['API']['woo_client_id'] = self.txt_woo_id.text().strip()
        self.config['API']['woo_client_secret'] = self.txt_woo_secret.text().strip()
        
        self.save_config_file()
        self.settings_changed.emit()
        self.accept()
