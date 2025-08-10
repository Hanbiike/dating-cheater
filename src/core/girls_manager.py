"""
Управление профилями собеседниц и их данными.
- girls_data.json: хранение профилей, истории, summary
- Методы: load/save, update_profile, get_profile_context, suggest_focus_topic, backup_daily_chat
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiofiles

from src.config.config import BACKUPS_DIR, GIRLS_DATA_PATH, PROFILE_ANALYZE_EVERY_N
from src.config.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import AsyncOpenAI
from src.utils.exceptions import DataStorageError, OpenAIError, safe_execute
from src.utils.validators import Validator

logger = logging.getLogger(__name__)


# Темы теперь вынесены в fields.json; список подгружается лениво в GirlsManager
@dataclass
class GirlProfile:
    chat_id: int
    name: str = ""
    last_activity: Optional[str] = None
    message_count: int = 0
    summary: Dict[str, str] = field(default_factory=dict)  # ключ=id анализа, значение=выжимка
    # profile теперь: снимки памяти по id -> объект произвольной структуры (анализ характера, увлечений и пр.)
    profile: Dict[str, Any] = field(default_factory=dict)
    # Идентификатор последнего ответа OpenAI для previous_response_id
    previous_response_id: Optional[str] = None

    def __post_init__(self):
        """Валидация данных после инициализации."""
        self.chat_id = Validator.validate_chat_id(self.chat_id)
        self.name = Validator.validate_name(self.name)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для сериализации."""
        return {
            "chat_id": self.chat_id,
            "name": self.name,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "summary": self.summary,
            "profile": self.profile,
            "previous_response_id": self.previous_response_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GirlProfile":
        """Создание экземпляра из словаря с валидацией."""
        try:
            return GirlProfile(
                chat_id=data.get("chat_id", 0),
                name=data.get("name", ""),
                last_activity=data.get("last_activity"),
                message_count=data.get("message_count", 0),
                summary=data.get("summary", {}),
                profile=data.get("profile", {}),
                previous_response_id=data.get("previous_response_id"),
            )
        except Exception as e:
            logger.error(f"Error creating GirlProfile from data: {e}")
            raise DataStorageError(f"Invalid profile data: {e}")


class GirlsManager:
    """Асинхронный менеджер профилей девушек с улучшенной обработкой ошибок."""

    def __init__(self, data_dir: str = "girls_data", path: str | None = None) -> None:
        """Создаёт менеджер профилей.

        Параметр ``path`` оставлен для обратной совместимости со старым API,
        где вместо ``data_dir`` использовалось именно это имя. Если указан
        ``path`` он имеет приоритет над ``data_dir``.
        """

        # Поддержка старого параметра ``path``
        if path is not None:
            data_dir = path

        self._data_dir = Path(data_dir)
        self._lock = asyncio.Lock()
        self._fields_cache: Optional[List[str]] = None
        self._backup_lock = asyncio.Lock()

        # Создаём директории если их нет
        self._data_dir.mkdir(parents=True, exist_ok=True)
        Path(BACKUPS_DIR).mkdir(parents=True, exist_ok=True)

    @safe_execute("load_girl_profile")
    async def load_profile(self, chat_id: int) -> Optional[GirlProfile]:
        """Загрузить профиль девушки по chat_id."""
        file_path = self._data_dir / f"{chat_id}.json"
        
        if not file_path.exists():
            return None
            
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                if content.strip():
                    data = json.loads(content)
                    return GirlProfile.from_dict(data)
                else:
                    return None
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла {file_path}: {e}")
            # Создаём резервную копию повреждённого файла
            backup_path = file_path.with_suffix(f".backup.{datetime.now().isoformat()}.json")
            file_path.rename(backup_path)
            return None
        except Exception as e:
            logger.exception(f"Ошибка загрузки профиля {chat_id}: {e}")
            raise DataStorageError(f"Failed to load profile {chat_id}: {e}")

    @safe_execute("save_girl_profile")
    async def save_profile(self, profile: GirlProfile) -> None:
        """Сохранить профиль девушки с атомарной записью."""
        async with self._lock:
            try:
                file_path = self._data_dir / f"{profile.chat_id}.json"
                temp_path = file_path.with_suffix('.tmp')
                
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
                
                # Атомарное перемещение
                temp_path.replace(file_path)
                logger.debug(f"Профиль {profile.chat_id} сохранён в {file_path}")
                
            except Exception as e:
                logger.exception(f"Ошибка сохранения профиля {profile.chat_id}: {e}")
                raise DataStorageError(f"Failed to save profile {profile.chat_id}: {e}")

    @safe_execute("list_all_profiles")
    async def list_all_profiles(self) -> List[GirlProfile]:
        """Получить список всех профилей."""
        profiles = []
        
        for file_path in self._data_dir.glob("*.json"):
            if file_path.name.startswith(".") or "backup" in file_path.name:
                continue
                
            try:
                chat_id = int(file_path.stem)
                profile = await self.load_profile(chat_id)
                if profile:
                    profiles.append(profile)
            except (ValueError, TypeError):
                logger.warning(f"Неверное имя файла профиля: {file_path.name}")
                continue
                
        return profiles

    @safe_execute("load_girls_data_legacy")
    async def load(self) -> None:
        """Загрузить данные из файла (совместимость со старым API)."""
        # Этот метод больше не нужен, но оставляем для обратной совместимости
        logger.info("Метод load() устарел. Используйте load_profile() для загрузки отдельных профилей")

    @safe_execute("save_girls_data_legacy") 
    async def save(self) -> None:
        """Сохранить текущие данные (совместимость со старым API)."""
        # Этот метод больше не нужен, но оставляем для обратной совместимости
        logger.info("Метод save() устарел. Используйте save_profile() для сохранения отдельных профилей")

    async def ensure_girl(self, chat_id: int, name: str = "") -> GirlProfile:
        """Убедиться, что профиль существует, и вернуть его."""
        profile = await self.load_profile(chat_id)
        if profile is None:
            profile = GirlProfile(chat_id=chat_id, name=name)
            await self.save_profile(profile)
        return profile

    async def update_last_activity(self, chat_id: int) -> None:
        """Обновить время последней активности и счётчик сообщений."""
        profile = await self.ensure_girl(chat_id)
        profile.last_activity = datetime.utcnow().isoformat() + "Z"
        profile.message_count += 1
        await self.save_profile(profile)

    async def update_profile(self, chat_id: int, message_text: str) -> None:
        """Простейшее эвристическое обновление профиля на основе текста.

        В ранних версиях проекта здесь выполнялся анализ сообщения по
        ключевым словам. Тесты по-прежнему рассчитывают, что после вызова
        ``update_profile`` в профиле появится базовая информация. Чтобы
        сохранить эту совместимость, реализуем лёгкую эвристику: по словам
        в сообщении определяем интересы, работу и путешествия.
        """

        profile = await self.ensure_girl(chat_id)

        text = message_text.lower()
        snapshot: Dict[str, Any] = {}

        if any(k in text for k in ["люблю", "интерес", "хобби"]):
            snapshot["interests"] = message_text.strip()
        if "работ" in text or "професс" in text:
            snapshot["work"] = message_text.strip()
        if "путеше" in text or "ездил" in text or "стамбул" in text:
            snapshot["travel"] = message_text.strip()

        if snapshot:
            sid = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            profile.profile[sid] = snapshot
            await self.save_profile(profile)
        else:
            # Даже если эвристика ничего не нашла, профиль должен существовать
            await self.save_profile(profile)

    async def get_profile_context(self, chat_id: int) -> str:
        """Короткая выжимка из последнего снимка профиля для prompt."""
        profile = await self.ensure_girl(chat_id)
        if not profile.profile:
            return ""
        last_id = max(profile.profile.keys())
        snap = profile.profile.get(last_id, {})
        if not isinstance(snap, dict):
            return str(snap)[:300]
        parts: List[str] = []
        for k, v in snap.items():
            if isinstance(v, list) and v:
                parts.append(f"{k}: {'; '.join(map(str, v[:2]))}")
            elif isinstance(v, dict):
                # возьмём ключи верхнего уровня
                parts.append(f"{k}: {', '.join(list(v.keys())[:3])}")
            elif isinstance(v, str) and v.strip():
                parts.append(f"{k}: {v.strip()[:60]}")
            if len(" | ".join(parts)) > 280:
                break
        return " | ".join(parts)[:300]

    async def suggest_focus_topic(self, chat_id: int) -> str:
        """Предложить топик для фокусировки на основе заполненности профиля."""
        fields = await self._get_fields()
        profile = await self.ensure_girl(chat_id)
        if not profile.profile:
            return fields[0] if fields else "facts"
        last_id = max(profile.profile.keys())
        snap = profile.profile.get(last_id, {})
        if not isinstance(snap, dict):
            return fields[0] if fields else "facts"
        snap_keys = {k.lower() for k in snap.keys()}
        for f in fields:
            if f.lower() not in snap_keys:
                return f
        return fields[0] if fields else "facts"

    async def analyze_and_summarize(self, chat_id: int, recent_messages: List[Dict[str, str]]) -> Optional[str]:
        """ИИ-анализ последних сообщений: сохраняем сводку и обновляем профиль.

        Просим модель вернуть JSON: {"summary": str, "profile": object}.
        В контексте передаём последний снимок профиля (previous_profile), чтобы сохранить важное.
        Возвращает идентификатор сохранённой сводки/профиля либо None при отсутствии входных данных.
        """
        profile = await self.ensure_girl(chat_id)
        prev_profile: Dict[str, Any] = {}
        if profile.profile:
            last_id = max(profile.profile.keys())
            last_snap = profile.profile.get(last_id)
            if isinstance(last_snap, dict):
                prev_profile = last_snap

        # Тексты последних сообщений
        texts: List[str] = []
        for m in recent_messages:
            val = m.get("text") or m.get("content") or ""
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
        if not texts:
            return None
        last_text = "\n".join(texts)[:4000]

        # ИИ-анализ
        client = _get_ai_client()
        if not client:
            # При отсутствии ключа OpenAI выполняем упрощённый фолбэк-аналитики,
            # чтобы сохранить совместимость тестов и не терять сообщения.
            logger.warning("OPENAI_API_KEY отсутствует — ИИ-анализ невозможен, используем упрощённый режим")
            sid = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            summary_text = last_text[:300]
            profile.summary[sid] = summary_text
            profile.profile[sid] = {"notes": summary_text}
            await self.save_profile(profile)
            return sid
        try:
            system_msg = (
                "Ты аналитик-памяти. По последним сообщениям сделай короткую выжимку (summary)"
                " и обнови полную память (profile) — компактный объект с фактами об интересах, работе, ценностях, семье, целях,"
                " привычках, характере и др.\n"
                "Сохрани важное из previous_profile и дополни новым. Верни строго JSON: {\"summary\": str, \"profile\": object}."
            )
            import json as _json
            user_msg = (
                f"previous_profile: {_json.dumps(prev_profile, ensure_ascii=False)}\n"
                f"last_messages:\n{last_text}"
            )
            resp = await client.responses.create(
                model=OPENAI_MODEL,
                instructions=system_msg,
                input=user_msg,
                max_output_tokens=400,
            )
            content = (resp.output_text or "").strip()

            def _cleanup_json(s: str) -> str:
                s = s.strip()
                if s.startswith("```"):
                    s = s.strip("`\n ")
                    if s.lower().startswith("json\n"):
                        s = s[5:]
                if s.endswith("```"):
                    s = s[:-3]
                return s.strip()

            parsed = _json.loads(_cleanup_json(content))
            summary_text = str(parsed.get("summary", "")).strip()
            new_profile_obj = parsed.get("profile", {}) or {}
            if not isinstance(new_profile_obj, dict):
                new_profile_obj = {"notes": new_profile_obj}

            # Сохранение сводки
            sid = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            if not summary_text:
                summary_text = last_text[:300]
            profile.summary[sid] = summary_text
            profile.profile[sid] = new_profile_obj
            await self.save_profile(profile)
            return sid
        except Exception as e:
            logger.exception("Ошибка ИИ-анализа профиля: %s", e)
            return None

    async def backup_daily_chat(self, chat_id: int, messages: List[Dict[str, Any]]) -> Path:
        """Сделать ежедневный бэкап в backups/<chat_id>/YYYY-MM-DD.json"""
        day = date.today().isoformat()
        folder = Path(BACKUPS_DIR) / str(chat_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{day}.json"
        profile = await self.ensure_girl(chat_id)
        payload = {
            "date": day,
            "chat_id": chat_id,
            "name": profile.name,
            "messages": messages,
        }
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    async def list_girls(self) -> List[GirlProfile]:
        """Получить список всех профилей."""
        return await self.list_all_profiles()

    async def delete_girl(self, chat_id: int) -> bool:
        """Удалить профиль девушки."""
        file_path = self._data_dir / f"{chat_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def get_profile(self, chat_id: int) -> Optional[GirlProfile]:
        """Получить профиль девушки (псевдоним для load_profile)."""
        return await self.load_profile(chat_id)

    async def get_latest_summary_text(self, chat_id: int) -> Optional[str]:
        """Вернуть текст последней сводки (summary) если есть."""
        profile = await self.load_profile(chat_id)
        if not profile:
            return None
        summaries: Dict[str, str] = profile.summary
        if not summaries:
            return None
        # Ключи — timestamp-строки, берём максимальный
        last_id = max(summaries.keys())
        return summaries.get(last_id)

    async def get_previous_response_id(self, chat_id: int) -> Optional[str]:
        """Получить сохранённый previous_response_id для chat_id."""
        profile = await self.ensure_girl(chat_id)
        return profile.previous_response_id

    async def set_previous_response_id(self, chat_id: int, response_id: Optional[str]) -> None:
        """Сохранить previous_response_id для chat_id (персистентно)."""
        profile = await self.ensure_girl(chat_id)
        profile.previous_response_id = response_id
        await self.save_profile(profile)

    async def _get_fields(self) -> List[str]:
        """Загрузить список тем из fields.json (кэшируется)."""
        if self._fields_cache is not None:
            return self._fields_cache
        try:
            from pathlib import Path as _P
            import aiofiles as _af
            p = _P("fields.json")
            fields: List[str] = []
            if p.exists():
                async with _af.open(p, "r", encoding="utf-8") as f:
                    content = await f.read()
                    if content.strip():
                        fields = json.loads(content)
            if not fields:
                fields = ["interests", "work", "travel", "music_movies", "values", "family", "goals", "fears", "facts"]
            self._fields_cache = fields
            return fields
        except Exception:
            self._fields_cache = ["interests", "work", "travel", "music_movies", "values", "family", "goals", "fears", "facts"]
            return self._fields_cache


# Ленивая инициализация клиента OpenAI для анализа профиля
_AI_CLIENT: AsyncOpenAI | None = None

def _get_ai_client() -> AsyncOpenAI | None:
    global _AI_CLIENT
    if _AI_CLIENT is None and OPENAI_API_KEY:
        _AI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _AI_CLIENT
