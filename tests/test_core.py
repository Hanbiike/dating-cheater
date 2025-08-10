"""
Тесты для проверки функции генерации ответов.
Использует моки для имитации OpenAI API без реальных запросов.
Также включает тесты реального API (опционально).
"""

import asyncio
import sys
import unittest.mock
from unittest.mock import AsyncMock, MagicMock

from response_generator import ResponseGenerator
from config import OPENAI_API_KEY, OPENAI_MODEL

# Доп. импорты для новых тестов
import os
import json
import types
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch


async def test_config_validation():
    """Проверка конфигурации OpenAI."""
    print("=== Проверка конфигурации ===")
    
    print(f"API ключ установлен: {'✅' if OPENAI_API_KEY else '❌'}")
    print(f"Модель: {OPENAI_MODEL}")
    
    if not OPENAI_API_KEY:
        print("⚠️  OPENAI_API_KEY не установлен в .env файле")
        print("   Создайте .env файл с: OPENAI_API_KEY=your_key_here")
    else:
        print(f"✅ API ключ длиной {len(OPENAI_API_KEY)} символов")


async def test_real_api_connection():
    """Тест реального API соединения (только при наличии ключа)."""
    print("\n=== Тест реального API ===")
    
    if not OPENAI_API_KEY:
        print("❌ Пропущен: нет API ключа")
        return
    
    print("🔄 Проверяем соединение с OpenAI...")
    
    rg = ResponseGenerator()
    if not rg._client:
        print("❌ Клиент не инициализирован")
        return
    
    try:
        # Простой тест с минимальным запросом
        response = await rg.generate(
            chat_id=999999,
            user_message="Привет",
            profile_context="",
            focus_topic=""
        )
        
        print(f"✅ API работает! Ответ: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        if "api_key" in str(e).lower():
            print("   Возможно, неверный API ключ")
        elif "quota" in str(e).lower():
            print("   Возможно, исчерпана квота")
        elif "model" in str(e).lower():
            print("   Возможно, недоступна модель")
        return False


async def test_api_with_full_context():
    """Тест реального API с полным контекстом."""
    print("\n=== Тест API с полным контекстом ===")
    
    if not OPENAI_API_KEY:
        print("❌ Пропущен: нет API ключа")
        return
    
    rg = ResponseGenerator()
    if not rg._client:
        print("❌ Клиент не инициализирован")
        return
    
    try:
        response = await rg.generate(
            chat_id=888888,
            user_message="Рассказал бы о своих увлечениях",
            profile_context="Девушка 25 лет, работает дизайнером, любит книги",
            focus_topic="хобби и интересы",
            summary_text="Обсуждали работу и творчество",
            system_goal="узнать больше об интересах"
        )
        
        print(f"✅ Ответ с контекстом: {response}")
        
        # Проверяем историю
        history = rg.get_recent_history(888888)
        print(f"📝 История: {len(history)} сообщений")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def test_basic_generation():
    """Базовый тест генерации с моком OpenAI."""
    print("=== Тест базовой генерации ===")
    
    # Создаем мок ответа
    mock_response = MagicMock()
    mock_response.output_text = "Привет! Как дела? Расскажи что-нибудь интересное!"
    
    # Создаем мок клиента
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=mock_response)
    
    # Создаем генератор и подменяем клиента
    rg = ResponseGenerator()
    rg._client = mock_client
    
    # Тестируем генерацию
    response = await rg.generate(
        chat_id=12345,
        user_message="Привет!",
        profile_context="Любит путешествия",
        focus_topic="хобби"
    )
    
    print(f"Ответ: {response}")
    print(f"История: {rg.get_recent_history(12345)}")
    
    # Проверяем, что клиент был вызван
    mock_client.responses.create.assert_called_once()
    assert response == "Привет! Как дела? Расскажи что-нибудь интересное!"


async def test_fallback_without_client():
    """Тест фолбэка при отсутствии клиента."""
    print("\n=== Тест фолбэка без клиента ===")
    
    rg = ResponseGenerator()
    rg._client = None  # Имитируем отсутствие клиента
    
    response = await rg.generate(
        chat_id=67890,
        user_message="Как дела?",
        profile_context="",
        focus_topic=""
    )
    
    print(f"Фолбэк ответ: {response}")
    print(f"История: {rg.get_recent_history(67890)}")


async def test_history_management():
    """Тест управления историей сообщений."""
    print("\n=== Тест управления историей ===")
    
    rg = ResponseGenerator()
    chat_id = 11111
    
    # Добавляем несколько сообщений
    for i in range(5):
        rg.add_to_history(chat_id, "user", f"Сообщение {i}")
        rg.add_to_history(chat_id, "assistant", f"Ответ {i}")
    
    history = rg.get_recent_history(chat_id)
    print(f"Количество сообщений в истории: {len(history)}")
    print("Последние сообщения:")
    for msg in history[-4:]:
        print(f"  {msg['role']}: {msg['content']}")


async def test_error_handling():
    """Тест обработки ошибок API."""
    print("\n=== Тест обработки ошибок ===")
    
    # Мок клиента, который выбрасывает ошибку
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(side_effect=Exception("API Error"))
    
    rg = ResponseGenerator()
    rg._client = mock_client
    
    response = await rg.generate(
        chat_id=99999,
        user_message="Тест ошибки",
        profile_context="",
        focus_topic=""
    )
    
    print(f"Ответ при ошибке: {response}")
    assert response == "Как прошёл твой день?"


async def test_complex_context():
    """Тест с полным контекстом."""
    print("\n=== Тест с полным контекстом ===")
    
    mock_response = MagicMock()
    mock_response.output_text = "Понятно, что работа в IT может быть стрессовой. Как ты справляешься с нагрузкой?"
    
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=mock_response)
    
    rg = ResponseGenerator()
    rg._client = mock_client
    
    response = await rg.generate(
        chat_id=55555,
        user_message="Сегодня был тяжелый день на работе",
        profile_context="Работает программистом, любит книги и кофе",
        focus_topic="работа и стресс",
        summary_text="Обсуждали карьеру в IT",
        system_goal="поддержать и выяснить способы релаксации"
    )
    
    print(f"Ответ: {response}")
    
    # Проверяем, что в вызов передались все контексты
    call_args = mock_client.responses.create.call_args
    instructions = call_args.kwargs['instructions']
    print(f"Инструкции включают:")
    print(f"  - Профиль: {'программистом' in instructions}")
    print(f"  - Фокус: {'работа и стресс' in instructions}")
    print(f"  - Сводка: {'карьеру в IT' in instructions}")
    print(f"  - Цель: {'поддержать' in instructions}")


async def test_conversation_flow():
    """Тест потока разговора."""
    print("\n=== Тест потока разговора ===")
    
    # Разные ответы для имитации диалога
    responses = [
        "Привет! Как у тебя дела?",
        "Звучит интересно! А что именно тебе нравится в этом?",
        "Понимаю. А есть планы на выходные?"
    ]
    
    mock_client = AsyncMock()
    rg = ResponseGenerator()
    rg._client = mock_client
    
    chat_id = 77777
    user_messages = [
        "Привет!",
        "Хорошо, сегодня изучал новую технологию",
        "Планирую встретиться с друзьями"
    ]
    
    for i, user_msg in enumerate(user_messages):
        mock_response = MagicMock()
        mock_response.output_text = responses[i]
        mock_client.responses.create = AsyncMock(return_value=mock_response)
        
        response = await rg.generate(
            chat_id=chat_id,
            user_message=user_msg,
            profile_context="IT специалист",
            focus_topic="хобби"
        )
        
        print(f"Пользователь: {user_msg}")
        print(f"Бот: {response}")
        print()
    
    print(f"Финальная история ({len(rg.get_recent_history(chat_id))} сообщений):")
    for msg in rg.get_recent_history(chat_id):
        role_name = "Пользователь" if msg['role'] == "user" else "Бот"
        print(f"  {role_name}: {msg['content']}")


async def test_conversation_initiator_time_of_day_and_generate():
    """Проверка time_of_day() и generate_starter()."""
    print("\n=== Тест conversation_initiator ===")
    import conversation_initiator as ci

    # Патчим datetime в модуле для проверки всех интервалов
    class DummyDT:
        @classmethod
        def now(cls):
            class T: pass
            o = T()
            o.hour = DummyDT._h
            return o

    with patch.object(ci, 'datetime', DummyDT):
        for h, expected in [(6, "утро"), (13, "день"), (19, "вечер"), (2, "ночь")]:
            DummyDT._h = h
            tod = ci.time_of_day()
            print(f"{h}:00 => {tod}")
            assert tod == expected

    # generate_starter вызывает rg.generate с нужными параметрами
    class RG:
        def __init__(self):
            self.calls = []
        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            return "starter"

    rg = RG()
    out = await ci.generate_starter(rg, 123, "ctx", "topic")
    assert out == "starter"
    assert rg.calls and rg.calls[0]["chat_id"] == 123
    assert "инициация" in rg.calls[0]["user_message"]


async def test_autonomous_manager_tick_and_followup():
    """Проверка AutonomousManager._tick() и plan_followup()."""
    print("\n=== Тест AutonomousManager ===")
    import autonomous_manager as am

    # Моки для менеджера девушек
    class G: chat_id = 111
    girls = MagicMock()
    girls.list_girls = AsyncMock(return_value=[G()])
    girls.get_profile_context = AsyncMock(return_value="ctx")
    girls.suggest_focus_topic = AsyncMock(return_value="topic")

    # Мок RG не используется напрямую, но обязателен
    rg = MagicMock()

    sent = []
    async def send_message(cid, text):
        sent.append((cid, text))

    is_stopping = lambda: False

    mgr = am.AutonomousManager(girls, rg, send_message, is_stopping, send_typing=None)

    with patch.object(am, 'now_allowed_hours', return_value=True), \
         patch('autonomous_manager.random.random', return_value=0.0), \
         patch('autonomous_manager.random.randint', return_value=1), \
         patch('autonomous_manager.generate_starter', new=AsyncMock(return_value='auto_starter')), \
         patch('autonomous_manager.asyncio.sleep', new=AsyncMock()):
        await mgr._tick()
        assert sent and sent[0] == (111, 'auto_starter')
        # Последняя отправка зафиксирована
        assert 111 in mgr._last_sent

    # plan_followup
    sent.clear()
    with patch('autonomous_manager.random.random', return_value=0.0), \
         patch('autonomous_manager.random.randint', return_value=1), \
         patch('autonomous_manager.generate_starter', new=AsyncMock(return_value='followup')), \
         patch('autonomous_manager.asyncio.sleep', new=AsyncMock()), \
         patch.object(mgr, '_send_typing', new=AsyncMock()):
        await mgr.plan_followup(222)
        assert sent and sent[0] == (222, 'followup')
        mgr._send_typing.assert_called()


async def test_admin_commands():
    """Проверка ключевых админ-команд."""
    print("\n=== Тест Admin ===")
    import admin as admin_mod

    # Моки окружения
    girls = MagicMock()
    girls.list_girls = AsyncMock(return_value=[])
    girls.ensure_girl = AsyncMock(side_effect=lambda cid, name: types.SimpleNamespace(chat_id=cid, name=name))
    girls.get_profile = AsyncMock(return_value=None)
    girls.delete_girl = AsyncMock(return_value=True)
    girls.get_profile_context = AsyncMock(return_value="ctx")
    girls.suggest_focus_topic = AsyncMock(return_value="topic")

    sent = []
    async def send_message(cid, text):
        sent.append((cid, text))
    stopped = {"v": False}
    def request_stop():
        stopped["v"] = True

    rg = MagicMock()

    async def resolve_identity(q: str) -> str:
        return f"Resolved: {q}"

    # Патчим ADMIN_CHAT_ID внутри модуля admin, чтобы команды считались админскими
    with patch.object(admin_mod, 'ADMIN_CHAT_ID', 555555):
        admin = admin_mod.Admin(girls, send_message, request_stop, rg, resolve_identity)
        aid = 555555

        # !help
        await admin.handle_admin_command(aid, "!help")
        # !id без параметров
        await admin.handle_admin_command(aid, "!id")
        # !id c параметром
        await admin.handle_admin_command(aid, "!id @username")

        # !add, !list, !del, !profile
        await admin.handle_admin_command(aid, "!add 12345 Alice")
        await admin.handle_admin_command(aid, "!list")
        await admin.handle_admin_command(aid, "!del 12345")
        await admin.handle_admin_command(aid, "!profile 12345")

        # !start инициирует диалог
        with patch.object(admin_mod, 'generate_starter', new=AsyncMock(return_value='hi there')):
            await admin.handle_admin_command(aid, "!start 12345")
        # !stop
        await admin.handle_admin_command(aid, "!stop")

    assert any("hi there" in m[1] for m in sent)
    assert stopped["v"] is True


async def test_girls_manager_end_to_end():
    """E2E тест чтения/записи профилей и бэкапа."""
    print("\n=== Тест GirlsManager ===")
    from girls_manager import GirlsManager
    import girls_manager as gm_mod

    with tempfile.TemporaryDirectory() as td:
        data_path = Path(td) / "girls.json"
        gm = GirlsManager(path=str(data_path))
        await gm.load()

        gp = await gm.ensure_girl(42, "Eva")
        assert gp.chat_id == 42

        # Профиль и активность
        await gm.update_profile(42, "Люблю книги и работаю дизайнером. Недавно путешествовала в Стамбул")
        await gm.update_last_activity(42)

        ctx = await gm.get_profile_context(42)
        assert "interests" in ctx or "work" in ctx or "travel" in ctx

        topic = await gm.suggest_focus_topic(42)
        assert isinstance(topic, str) and topic

        # Накручиваем счётчик до кратного PROFILE_ANALYZE_EVERY_N
        from config import PROFILE_ANALYZE_EVERY_N
        for _ in range(PROFILE_ANALYZE_EVERY_N - 1):
            await gm.update_last_activity(42)
        sid = await gm.analyze_and_summarize(42, [{"text": "interests and values"}])
        assert sid is not None

        # Бэкап в свою папку, патчим константу модуля
        with patch.object(gm_mod, 'BACKUPS_DIR', str(Path(td) / 'bk')):
            p = await gm.backup_daily_chat(42, [{"text": "hi"}])
            assert p.exists()


async def test_logger_append_and_setup():
    """Проверка логгера и записи диалогов."""
    print("\n=== Тест Logger ===")
    import logger as logmod

    logmod.setup_logging()
    root = __import__('logging').getLogger()
    assert root.handlers

    with tempfile.TemporaryDirectory() as td:
        with patch.object(logmod, 'CONVERSATIONS_DIR', td):
            await logmod.append_conversation(123, {"direction": "in", "text": "hello"})
            p = Path(td) / "123.json"
            assert p.exists()
            data = json.loads(p.read_text(encoding='utf-8'))
            assert isinstance(data, list) and data and data[0]["text"] == "hello"


async def test_shutdown_handler():
    """Проверка Shutdown.request_stop()/wait()."""
    print("\n=== Тест Shutdown ===")
    from shutdown_handler import Shutdown
    sh = Shutdown()
    # install может не поддерживаться на платформе — просто вызываем
    try:
        sh.install()
    except Exception:
        pass
    sh.request_stop()
    await sh.wait()
    assert sh.is_stopping() is True


async def test_config_basics():
    """Проверка базовых настроек config."""
    print("\n=== Тест config ===")
    import config as cfg
    assert isinstance(cfg.OPENAI_MODEL, str)
    assert isinstance(cfg.HISTORY_LIMIT, int)
    assert 0 < cfg.OPENAI_MAX_TOKENS
    assert 0.0 <= cfg.OPENAI_TEMPERATURE <= 2.0


async def test_main_smoke():
    """Лёгкий smoke-тест: модуль импортируется, функция main существует."""
    print("\n=== Smoke main ===")
    import importlib
    m = importlib.import_module('main')
    assert hasattr(m, 'main') and asyncio.iscoroutinefunction(m.main)


async def main():
    """Запуск всех тестов."""
    print("🤖 Тестирование ResponseGenerator\n")

    # Проверяем аргументы командной строки
    test_real_api = "--real-api" in sys.argv

    # Базовые тесты с моками (всегда)
    await test_config_validation()
    await test_basic_generation()
    await test_fallback_without_client()
    await test_history_management()
    await test_error_handling()
    await test_complex_context()
    await test_conversation_flow()

    # Новые тесты по остальным модулям
    await test_conversation_initiator_time_of_day_and_generate()
    await test_autonomous_manager_tick_and_followup()
    await test_admin_commands()
    await test_girls_manager_end_to_end()
    await test_logger_append_and_setup()
    await test_shutdown_handler()
    await test_config_basics()
    await test_main_smoke()

    # Реальные API тесты (опционально)
    if test_real_api:
        print("\n" + "="*50)
        print("🌐 ТЕСТЫ РЕАЛЬНОГО API")
        print("="*50)

        api_works = await test_real_api_connection()
        if api_works:
            await test_api_with_full_context()
    else:
        print("\n💡 Для тестирования реального API запустите:")
        print("   python test.py --real-api")

    print("\n✅ Все тесты завершены!")


if __name__ == "__main__":
    asyncio.run(main())
