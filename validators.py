"""
Валидация данных для бота Han.
Обеспечивает проверку корректности входных данных и конфигурации.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from exceptions import ValidationError


class Validator:
    """Класс для валидации различных типов данных."""
    
    @staticmethod
    def validate_chat_id(chat_id: Any) -> int:
        """Валидация chat_id."""
        if not isinstance(chat_id, int):
            try:
                chat_id = int(chat_id)
            except (ValueError, TypeError):
                raise ValidationError(f"Invalid chat_id: {chat_id}", {"type": type(chat_id)})
        
        if chat_id == 0:
            raise ValidationError("chat_id cannot be zero")
            
        return chat_id
    
    @staticmethod
    def validate_message_text(text: Any) -> str:
        """Валидация текста сообщения."""
        if not isinstance(text, str):
            raise ValidationError(f"Message text must be string, got {type(text)}")
        
        text = text.strip()
        if not text:
            raise ValidationError("Message text cannot be empty")
            
        if len(text) > 4096:  # Telegram limit
            raise ValidationError(f"Message text too long: {len(text)} chars", {"max_length": 4096})
            
        return text
    
    @staticmethod
    def validate_name(name: Any) -> str:
        """Валидация имени пользователя."""
        if name is None:
            return ""
            
        if not isinstance(name, str):
            name = str(name)
            
        name = name.strip()
        if len(name) > 64:
            name = name[:64]
            
        return name
    
    @staticmethod
    def validate_api_key(api_key: Any) -> str:
        """Валидация API ключа."""
        if not isinstance(api_key, str):
            raise ValidationError("API key must be string")
            
        api_key = api_key.strip()
        if not api_key:
            raise ValidationError("API key cannot be empty")
            
        # Базовая проверка формата для OpenAI ключей (поддержка старых и новых форматов)
        if not re.match(r'^sk-[a-zA-Z0-9_-]+$', api_key):
            raise ValidationError("Invalid OpenAI API key format")
            
        return api_key
    
    @staticmethod
    def validate_phone_number(phone: Any) -> str:
        """Валидация номера телефона."""
        if not isinstance(phone, str):
            raise ValidationError("Phone number must be string")
            
        phone = phone.strip()
        if not phone:
            raise ValidationError("Phone number cannot be empty")
            
        # Убираем все кроме цифр и +
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        if not re.match(r'^\+\d{10,15}$', cleaned):
            raise ValidationError(f"Invalid phone number format: {phone}")
            
        return cleaned
    
    @staticmethod
    def validate_profile_data(data: Any) -> Dict[str, Any]:
        """Валидация данных профиля."""
        if not isinstance(data, dict):
            raise ValidationError(f"Profile data must be dict, got {type(data)}")
            
        # Проверяем размер данных
        import json
        json_str = json.dumps(data, ensure_ascii=False)
        if len(json_str) > 1024 * 1024:  # 1MB limit
            raise ValidationError("Profile data too large", {"size": len(json_str)})
            
        return data
    
    @staticmethod
    def validate_conversation_record(record: Any) -> Dict[str, Any]:
        """Валидация записи разговора."""
        if not isinstance(record, dict):
            raise ValidationError(f"Conversation record must be dict, got {type(record)}")
            
        required_fields = ['direction', 'text']
        for field in required_fields:
            if field not in record:
                raise ValidationError(f"Missing required field: {field}")
                
        if record['direction'] not in ['in', 'out']:
            raise ValidationError(f"Invalid direction: {record['direction']}")
            
        record['text'] = Validator.validate_message_text(record['text'])
        return record


def validate_config(config_dict: Dict[str, Any]) -> None:
    """
    Валидация конфигурации приложения.
    
    Args:
        config_dict: Словарь с конфигурацией
        
    Raises:
        ValidationError: При некорректной конфигурации
    """
    required_fields = [
        'TELEGRAM_API_ID',
        'TELEGRAM_API_HASH', 
        'TELEGRAM_PHONE'
    ]
    
    for field in required_fields:
        if field not in config_dict or not config_dict[field]:
            raise ValidationError(f"Missing required config field: {field}")
    
    # Валидация Telegram настроек
    try:
        api_id = int(config_dict['TELEGRAM_API_ID'])
        if api_id <= 0:
            raise ValidationError("TELEGRAM_API_ID must be positive integer")
    except ValueError:
        raise ValidationError("TELEGRAM_API_ID must be integer")
    
    if not isinstance(config_dict['TELEGRAM_API_HASH'], str) or not config_dict['TELEGRAM_API_HASH']:
        raise ValidationError("TELEGRAM_API_HASH must be non-empty string")
    
    Validator.validate_phone_number(config_dict['TELEGRAM_PHONE'])
    
    # Валидация OpenAI (опционально)
    if config_dict.get('OPENAI_API_KEY'):
        Validator.validate_api_key(config_dict['OPENAI_API_KEY'])
    
    # Валидация админ chat_id
    if config_dict.get('ADMIN_CHAT_ID'):
        Validator.validate_chat_id(config_dict['ADMIN_CHAT_ID'])
