"""
Улучшенная админка управления базой девушек через команды в Telegram.
Команды (для ADMIN_CHAT_ID):
- !help - помощь
- !status - статус системы и метрики
- !list - список всех профилей 
- !add <chat_id> <name> - добавить профиль
- !del <chat_id> - удалить профиль
- !profile <chat_id> - показать профиль
- !start <chat_id> - инициировать диалог
- !id [query] - получить информацию о пользователе
- !metrics - показать детальные метрики
- !restart - перезапуск бота
- !stop - безопасная остановка
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional
import json

from config import ADMIN_CHAT_ID
from girls_manager import GirlsManager
from conversation_initiator import generate_starter
from exceptions import handle_exception
from validators import Validator
from metrics import metrics_collector

logger = logging.getLogger(__name__)


class Admin:
    """Улучшенная админка с расширенными командами и валидацией."""
    
    def __init__(
        self,
        girls: GirlsManager,
        send_message: Callable[[int, str], Awaitable[None]],
        request_stop: Callable[[], None],
        rg,  # ResponseGenerator
        resolve_identity: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._girls = girls
        self._send = send_message
        self._request_stop = request_stop
        self._rg = rg
        self._resolve_identity = resolve_identity
        
        # Команды админки
        self._commands = {
            "!help": self._cmd_help,
            "!status": self._cmd_status,
            "!list": self._cmd_list,
            "!add": self._cmd_add,
            "!del": self._cmd_delete,
            "!profile": self._cmd_profile,
            "!start": self._cmd_start,
            "!id": self._cmd_id,
            "!metrics": self._cmd_metrics,
            "!restart": self._cmd_restart,
            "!stop": self._cmd_stop,
        }

    async def handle_admin_command(self, chat_id: int, text: str) -> bool:
        """Обработать админ-команду. Возвращает True если это была команда админа."""
        if chat_id != ADMIN_CHAT_ID:
            return False
            
        try:
            parts = text.strip().split()
            if not parts:
                return True
                
            cmd = parts[0].lower()
            if cmd not in self._commands:
                await self._send(chat_id, f"Неизвестная команда: {cmd}. Используйте !help")
                return True
                
            await self._commands[cmd](chat_id, parts)
            return True
            
        except Exception as e:
            handle_exception(e, "admin_command", command=text)
            await self._send(chat_id, f"Ошибка выполнения команды: {str(e)}")
            return True

    async def _cmd_help(self, chat_id: int, parts: list) -> None:
        """Команда помощи."""
        help_text = """
🤖 **Команды администратора:**

📊 **Информация:**
• `!status` - статус системы
• `!metrics` - детальные метрики
• `!list` - список профилей
• `!profile <chat_id>` - показать профиль

👥 **Управление профилями:**
• `!add <chat_id> <name>` - добавить профиль
• `!del <chat_id>` - удалить профиль
• `!start <chat_id>` - инициировать диалог

🔍 **Утилиты:**
• `!id [query]` - информация о пользователе
• `!restart` - перезапуск бота
• `!stop` - остановка бота

💡 **Примеры:**
`!add 123456789 Анна`
`!id @username`
`!profile 123456789`
        """
        await self._send(chat_id, help_text)

    async def _cmd_status(self, chat_id: int, parts: list) -> None:
        """Показать статус системы."""
        try:
            summary = metrics_collector.get_summary()
            
            status_text = f"""
🤖 **Статус системы**

⏱ **Время работы:** {summary['uptime']}

📱 **Telegram:** {summary['status']['telegram']}
🧠 **OpenAI:** {summary['status']['openai']}

📊 **Сообщения:**
• Получено: {summary['messages']['received']}
• Отправлено: {summary['messages']['sent']}
• Соотношение: {summary['messages']['ratio']:.2f}

🔄 **API запросы:**
• Всего: {summary['api']['requests']}
• Неудачных: {summary['api']['failures']}
• Успешность: {summary['api']['success_rate']}

⚡ **Производительность:**
• Время ответа: {summary['performance']['avg_response_time']}
• Память: {summary['performance']['memory_usage']}
• Активных чатов: {summary['performance']['active_chats']}

❌ **Ошибки:** {summary['errors']}
            """
            await self._send(chat_id, status_text)
            
        except Exception as e:
            await self._send(chat_id, f"Ошибка получения статуса: {e}")

    async def _cmd_list(self, chat_id: int, parts: list) -> None:
        """Список всех профилей."""
        try:
            girls = await self._girls.list_girls()
            if not girls:
                await self._send(chat_id, "📭 Список пуст")
                return
                
            lines = ["👥 **Список профилей:**\n"]
            for i, g in enumerate(girls, 1):
                last_activity = ""
                if g.last_activity:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(g.last_activity.replace('Z', '+00:00'))
                        last_activity = f" (🕐 {dt.strftime('%d.%m %H:%M')})"
                    except:
                        pass
                        
                lines.append(f"{i}. `{g.chat_id}` — {g.name or 'без имени'}{last_activity}")
                
            await self._send(chat_id, "\n".join(lines))
            
        except Exception as e:
            await self._send(chat_id, f"Ошибка получения списка: {e}")

    async def _cmd_add(self, chat_id: int, parts: list) -> None:
        """Добавить профиль."""
        if len(parts) < 3:
            await self._send(chat_id, "❌ Формат: `!add <chat_id> <name>`")
            return
            
        try:
            target_id = Validator.validate_chat_id(parts[1])
            name = " ".join(parts[2:])
            name = Validator.validate_name(name)
            
            gp = await self._girls.ensure_girl(target_id, name)
            await self._send(chat_id, f"✅ Добавлен: `{gp.chat_id}` — {gp.name}")
            
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка добавления: {e}")

    async def _cmd_delete(self, chat_id: int, parts: list) -> None:
        """Удалить профиль."""
        if len(parts) != 2:
            await self._send(chat_id, "❌ Формат: `!del <chat_id>`")
            return
            
        try:
            target_id = Validator.validate_chat_id(parts[1])
            ok = await self._girls.delete_girl(target_id)
            
            if ok:
                await self._send(chat_id, f"✅ Профиль `{target_id}` удалён")
            else:
                await self._send(chat_id, f"❌ Профиль `{target_id}` не найден")
                
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка удаления: {e}")

    async def _cmd_profile(self, chat_id: int, parts: list) -> None:
        """Показать профиль."""
        if len(parts) != 2:
            await self._send(chat_id, "❌ Формат: `!profile <chat_id>`")
            return
            
        try:
            target_id = Validator.validate_chat_id(parts[1])
            gp = await self._girls.get_profile(target_id)
            
            if not gp:
                await self._send(chat_id, f"❌ Профиль `{target_id}` не найден")
                return
                
            profile_text = f"""
👤 **Профиль {gp.chat_id}**

📝 **Имя:** {gp.name or 'не указано'}
📊 **Сообщений:** {gp.message_count}
🕐 **Последняя активность:** {gp.last_activity or 'никогда'}

📋 **Сводки:** {len(gp.summary)}
🧠 **Снимков профиля:** {len(gp.profile)}

💾 **Данные:** ```json
{json.dumps(gp.to_dict(), ensure_ascii=False, indent=2)[:800]}
```
            """
            await self._send(chat_id, profile_text)
            
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка получения профиля: {e}")

    async def _cmd_start(self, chat_id: int, parts: list) -> None:
        """Инициировать диалог."""
        if len(parts) != 2:
            await self._send(chat_id, "❌ Формат: `!start <chat_id>`")
            return
            
        try:
            target_id = Validator.validate_chat_id(parts[1])
            
            existing = await self._girls.get_profile(target_id)
            is_new = existing is None
            
            if is_new:
                await self._girls.ensure_girl(target_id, "")
                
            profile_context = await self._girls.get_profile_context(target_id)
            focus_topic = await self._girls.suggest_focus_topic(target_id)
            starter = await generate_starter(self._rg, target_id, profile_context, focus_topic)
            
            await self._send(target_id, starter)
            
            status = "новый" if is_new else "существующий"
            await self._send(chat_id, f"✅ Диалог инициирован с `{target_id}` ({status})")
            
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка инициации диалога: {e}")

    async def _cmd_id(self, chat_id: int, parts: list) -> None:
        """Получить информацию о пользователе."""
        if len(parts) == 1:
            await self._send(chat_id, f"🆔 Ваш chat_id: `{chat_id}`")
            return
            
        if not self._resolve_identity:
            await self._send(chat_id, "❌ Резолвер недоступен")
            return
            
        query = parts[1]
        try:
            info = await self._resolve_identity(query)
            await self._send(chat_id, f"🔍 **Результат поиска:**\n{info}")
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка поиска: {e}")

    async def _cmd_metrics(self, chat_id: int, parts: list) -> None:
        """Показать детальные метрики."""
        try:
            metrics = metrics_collector.get_metrics()
            
            metrics_text = f"""
📊 **Детальные метрики**

⏱ **Время работы:** {metrics.uptime_formatted}
📱 **Получено сообщений:** {metrics.messages_received}
📤 **Отправлено сообщений:** {metrics.messages_sent}
🔄 **API запросов:** {metrics.api_requests}
❌ **API ошибок:** {metrics.api_failures}
🐛 **Всего ошибок:** {metrics.errors_count}
👥 **Активных чатов:** {metrics.active_chats}

⚡ **Производительность:**
• Среднее время ответа: {metrics.avg_response_time:.2f}s
• Память: {metrics.memory_usage_mb:.1f}MB
• Успешность API: {metrics.success_rate:.1f}%

🔗 **Соединения:**
• Telegram: {'✅' if metrics.telegram_connected else '❌'}
• OpenAI: {'✅' if metrics.openai_available else '❌'}
            """
            await self._send(chat_id, metrics_text)
            
        except Exception as e:
            await self._send(chat_id, f"❌ Ошибка получения метрик: {e}")

    async def _cmd_restart(self, chat_id: int, parts: list) -> None:
        """Перезапуск бота."""
        await self._send(chat_id, "🔄 Перезапуск пока не реализован")

    async def _cmd_stop(self, chat_id: int, parts: list) -> None:
        """Остановка бота."""
        await self._send(chat_id, "🛑 Останавливаюсь безопасно...")
        self._request_stop()
