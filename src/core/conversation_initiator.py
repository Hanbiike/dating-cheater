"""
Инициатор разговоров: генерирует стартовые сообщения с учётом времени суток.
Цель — мягко начать диалог и заполнять профиль собеседницы.
"""
from __future__ import annotations

from datetime import datetime

from src.core.response_generator import ResponseGenerator


def time_of_day() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:
        return "утро"
    if 12 <= h < 18:
        return "день"
    if 18 <= h < 23:
        return "вечер"
    return "ночь"


async def generate_starter(
    rg: ResponseGenerator,
    chat_id: int,
    profile_context: str,
    focus_topic: str,
) -> str:
    goal = (
        "Начни разговор ненавязчиво, со ссылкой на время суток, задай один короткий вопрос. "
        "Приоритет — узнать больше о собеседнице и дополнить её профиль."
    )
    return await rg.generate(
        chat_id=chat_id,
        user_message=f"[инициация разговора, сейчас {time_of_day()}]",
        profile_context=profile_context,
        focus_topic=focus_topic,
        system_goal=goal,
    )
