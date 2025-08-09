#!/usr/bin/env python3
"""
Скрипт миграции из girls_data.json в структуру girls_data/{chat_id}.json
"""
import json
import asyncio
from pathlib import Path
from girls_manager import GirlsManager, GirlProfile

async def migrate_data():
    """Миграция данных из старого формата в новый."""
    
    # Проверяем наличие старого файла
    old_file = Path("girls_data.json")
    new_dir = Path("girls_data")
    
    if not old_file.exists():
        print("❌ Файл girls_data.json не найден")
        return
        
    if new_dir.exists():
        print("✅ Папка girls_data уже существует")
        print("📁 Текущие файлы:")
        for file in new_dir.glob("*.json"):
            print(f"   - {file.name}")
        return
        
    print("🔄 Начинаем миграцию...")
    
    # Загружаем старые данные
    with open(old_file, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    
    girls_data = old_data.get("girls", {})
    print(f"📊 Найдено {len(girls_data)} профилей для миграции")
    
    # Создаём новую папку
    new_dir.mkdir(exist_ok=True)
    
    # Мигрируем каждый профиль
    gm = GirlsManager()
    
    for chat_id_str, profile_data in girls_data.items():
        try:
            profile = GirlProfile.from_dict(profile_data)
            await gm.save_profile(profile)
            print(f"✅ Мигрирован профиль {chat_id_str}: {profile.name}")
        except Exception as e:
            print(f"❌ Ошибка миграции профиля {chat_id_str}: {e}")
    
    # Создаём резервную копию старого файла
    backup_file = old_file.with_suffix(".backup.json")
    old_file.rename(backup_file)
    print(f"💾 Старый файл перемещён в {backup_file}")
    
    print("🎉 Миграция завершена!")

if __name__ == "__main__":
    asyncio.run(migrate_data())
