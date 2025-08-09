#!/usr/bin/env python3
"""
Быстрая проверка инициализации OpenAI клиента
"""

import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

def test_openai_setup():
    print("🔍 Проверка настройки OpenAI...")
    
    # Проверяем ключ
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("❌ OPENAI_API_KEY не установлен")
        return False
    
    print(f"✅ API ключ найден (длина: {len(api_key)})")
    print(f"   Формат: {api_key[:10]}...{api_key[-10:]}")
    
    # Проверяем модель
    model = os.getenv("OPENAI_MODEL", "")
    print(f"📝 Модель: {model}")
    
    # Тестируем валидацию
    try:
        from validators import Validator
        Validator.validate_api_key(api_key)
        print("✅ Валидация ключа прошла успешно")
    except Exception as e:
        print(f"❌ Ошибка валидации: {e}")
        return False
    
    # Тестируем инициализацию клиента
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        print("✅ OpenAI клиент создан успешно")
    except Exception as e:
        print(f"❌ Ошибка создания клиента: {e}")
        return False
        
    print("🎉 Всё настроено корректно!")
    return True

if __name__ == "__main__":
    test_openai_setup()
