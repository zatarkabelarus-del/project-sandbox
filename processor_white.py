import os
import numpy as np
from PIL import Image
from rembg import remove, new_session

INPUT_DIR = r"D:\Для очистки фона фотографий\Исходные фото"
OUTPUT_DIR = r"D:\Для очистки фона фотографий\Очищенные фото_white"
TARGET_SIZE = 820

print("--- Скрипт 2: ИДЕАЛЬНЫЙ УНИВЕРСАЛЬНЫЙ БЕЛЫЙ ФОН (JPEG) ---")
if not os.path.exists(INPUT_DIR):
    print("КРИТИЧЕСКАЯ ОШИБКА: Папка не найдена!")
    os.makedirs(INPUT_DIR, exist_ok=True)
    all_files = []
else:
    # ДОБАВЛЕНО: поддержка .tiff и .tif
    all_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.tiff', '.tif'))]
    print(f"Файлов обнаружено: {len(all_files)}")

os.makedirs(OUTPUT_DIR, exist_ok=True)
num_digits = max(2, len(str(len(all_files))))
processed_count = 0

session = new_session("u2net")

for index, filename in enumerate(all_files, start=1):
    input_path = os.path.join(INPUT_DIR, filename)
    file_number = str(index).zfill(num_digits)
    output_path = os.path.join(OUTPUT_DIR, f"{file_number}.jpg")
    
    try:
        img = Image.open(input_path).convert("RGBA")
        
        # 1. Быстрое удаление фона нейросетью
        img_no_bg = remove(img, session=session)
        
        # 2. Математический деспилл (зеленый -> нейтральный серый)
        cv_img = np.array(img_no_bg)
        r = cv_img[:, :, 0].astype(np.float32)
        g = cv_img[:, :, 1].astype(np.float32)
        b = cv_img[:, :, 2].astype(np.float32)
        
        rb_avg = (r + b) / 2.0
        green_excess = g > (rb_avg * 1.05)
        g[green_excess] = rb_avg[green_excess]
        
        cv_img[:, :, 1] = g.astype(np.uint8)
        img_no_bg = Image.fromarray(cv_img)
        
        # 3. Изменение размера и центрирование
        ratio = float(TARGET_SIZE) / max(img_no_bg.size)
        new_size = tuple([int(x * ratio) for x in img_no_bg.size])
        img_resized = img_no_bg.resize(new_size, Image.Resampling.LANCZOS)
        
        final_card = Image.new("RGB", (TARGET_SIZE, TARGET_SIZE), (255, 255, 255))
        upper_left_x = (TARGET_SIZE - new_size[0]) // 2
        upper_left_y = (TARGET_SIZE - new_size[1]) // 2
        
        final_card.paste(img_resized, (upper_left_x, upper_left_y), img_resized)
        final_card.save(output_path, "JPEG", quality=95)
        
        print(f"[Успех] {filename} -> {file_number}.jpg")
        processed_count += 1
    except Exception as e:
        print(f"[Ошибка] {filename}: {e}")

print(f"\nГотово! Создано JPG: {processed_count}")
