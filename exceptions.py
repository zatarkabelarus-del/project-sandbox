# server_backend/exceptions.py
class AppBaseException(Exception):
    """Базовое исключение для всего приложения"""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(self.message)

class AppNetworkError(AppBaseException):
    """Сбои связи, лимиты и таймауты внешних API"""
    def __init__(self, message: str):
        super().__init__(message, code=503)

class InvalidImageError(AppBaseException):
    """Битые файлы, неподдерживаемые форматы, пустые буферы"""
    def __init__(self, message: str):
        super().__init__(message, code=400)

class TokenValidationError(AppBaseException):
    """Недостаточно токенов для выполнения цепочки операций"""
    def __init__(self, message: str):
        super().__init__(message, code=402)
