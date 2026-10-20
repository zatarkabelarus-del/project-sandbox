import os
import sys

# Настройка путей, чтобы корень видел внутренности server_backend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "server_backend"))

from image_processing.pipeline import ImageProcessingPipeline

def run_main_pipeline():
    print("=== ЗАПУСК ПОЛНОГО СКВОЗНОГО КОНВЕЙЕРА ОБРАБОТКИ ===")
    
    source_raw = os.path.join(BASE_DIR, "Пульт.jpg")
    logo_path = os.path.join(BASE_DIR, "logo.png")
    output_card = os.path.join(BASE_DIR, "пульт_полный_результат.png")

    if not os.path.exists(source_raw):
        print(f"[🔴 ОШИБКА] В корне проекта не найден исходный сырой файл 'Пульт.jpg'!")
        return

    # 1. Создаем экземпляр конвейера (загрузка u2net)
    pipeline = ImageProcessingPipeline()

    # 2. Запускаем обработку «в одно нажатие»
    success = pipeline.process_item(
        source_path=source_raw,
        output_path=output_card,
        logo_path=logo_path,
        canvas_size=(1000, 1000),   # Целевой квадрат для сайта
        scale_percent=80.0,         # Объект займет 80% площади холста
        shadow_enabled=False,        # ВКЛЮЧАЕМ генерацию мягкой тени для объема!
        blur_radius=0               # Легкое сглаживание краев пикселей
    )

    if success:
        print("\n[🎉 ПОБЕДА!] Сквозной ИИ-конвейер отработал штатно.")
        print(f"[📄 ИТОГОВЫЙ ФАЙЛ]: {output_card}")
    else:
        print("\n[❌ ОШИБКА]: Сборка конвейера завершилась неудачей.")

if __name__ == "__main__":
    run_main_pipeline()
