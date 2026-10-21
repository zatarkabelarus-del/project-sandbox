import json
import os
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox
from PySide6.QtGui import QAction
from network.server_api import ServerAPI
from ui.settings_window import SettingsWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ServerAPI()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Загрузка товаров WooCommerce")
        self.resize(500, 400)
        
        # === ЯКОРЬ НАЧАЛА: Создание верхнего меню настроек ===
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Опции")
        
        open_settings_action = QAction("Настройки системы", self)
        open_settings_action.triggered.connect(self.show_settings_window)
        settings_menu.addAction(open_settings_action)
        # === ЯКОРЬ КОНЦА: Создание верхнего меню настроек ===
        
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        self.products_label = QLabel("Нажмите кнопку, чтобы загрузить товары с сайта...", self)
        self.products_label.setWordWrap(True)
        layout.addWidget(self.products_label)
        
        self.btn_load = QPushButton("Получить 5 товаров с zatarka.by", self)
        self.btn_load.clicked.connect(self.handle_load_products)
        layout.addWidget(self.btn_load)

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
