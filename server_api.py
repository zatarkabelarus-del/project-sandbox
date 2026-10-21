import requests

class ServerAPI:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url

    def check_connection(self):
        try:
            response = requests.get(self.base_url + "/api/health", timeout=5)
            return response.json().get("status") == "ok"
        except:
            return False

    def fetch_products(self):
        """Запрос к серверу для получения списка товаров"""
        try:
            print("[Клиент] Отправляю запрос на сервер за товарами...")
            response = requests.get(self.base_url + "/api/products", timeout=15)
            print(f"[Клиент] Код ответа от сервера: {response.status_code}")
            
            if response.status_code == 200:
                return response.json().get("products", [])
            return []
        except Exception as e:
            print(f"[Клиент] Ошибка при отправке запроса: {e}")
            return []
