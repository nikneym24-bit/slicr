# ЗАДАНИЕ: Этап 2b — Bot (aiogram) + Модерация + Команды

## Роль
Ты — исполнитель. Твоя задача — реализовать Telegram-бота на aiogram: модерацию видео (Approve/Reject в Tech-канале) и команды управления источниками (/add_source, /sources). Stage 2a уже реализован — TelegramClientWrapper и TelegramMonitor работают.

## Проект
- Путь: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /video-clipper/`
- Ветка: `stage-2/monitor-downloader` (ты на ней)
- Среда: macOS, Python 3.13, venv в `.venv/`

## Обязательно прочитай перед началом

### Проект video-clipper:
1. `docs/CLAUDE.md` — правила проекта, архитектура, правила импортов
2. `docs/MODULE_MAP.md` — карта модулей
3. `src/video_clipper/config.py` — конфиг (уже расширен в Stage 2a)
4. `src/video_clipper/constants.py` — enum-ы статусов
5. `src/video_clipper/database/models.py` — CRUD-методы
6. `src/video_clipper/services/telegram_client.py` — TelegramClientWrapper (реализован в Stage 2a)
7. `src/video_clipper/pipeline/monitor.py` — TelegramMonitor (реализован в Stage 2a)
8. Текущие заглушки: `bot/handlers.py`, `bot/moderation.py`, `bot/keyboards.py`
9. `src/video_clipper/__main__.py` — точка входа (будешь обновлять)

### Референс — TGForwardez (ИЗУЧИ и АДАПТИРУЙ):
| Что взять | Файл TGF | Как адаптировать |
|-----------|----------|------------------|
| /add_source: парсинг ID, URL, @username, forward | `/Users/dvofis/Desktop/Програмирование/TGForwardez/handlers/sources/add.py` | → `bot/handlers.py` — адаптировать под нашу БД и архитектуру |
| Модерация: inline кнопки, callback_query | `/Users/dvofis/Desktop/Програмирование/TGForwardez/handlers/moderation/callbacks.py` | → `bot/moderation.py` — упростить до Approve/Reject |
| Клавиатуры: InlineKeyboardMarkup | `/Users/dvofis/Desktop/Програмирование/TGForwardez/handlers/moderation/callbacks.py` (строки ~216-224) | → `bot/keyboards.py` |
| Bot startup: Dispatcher, Router, polling | `/Users/dvofis/Desktop/Програмирование/TGForwardez/bot.py` (строки ~82-88, ~128-140) | → `__main__.py` — добавить aiogram |

**ВАЖНО:**
- В TGF модерация сложная (TG, VK, Schedule, Back) — у нас MVP: только Approve / Reject
- В TGF много routers — у нас 2: handlers.py + moderation.py
- Бот работает через aiogram, мониторинг — через Telethon (два клиента одновременно)

---

## Архитектура

```
┌────────────────────────────────────────────────────────────┐
│  __main__.py                                                │
│  Создаёт:                                                   │
│    1. TelegramClientWrapper (Telethon) — для мониторинга    │
│    2. aiogram Bot + Dispatcher — для команд и модерации     │
│  Запускает параллельно:                                     │
│    - Telethon event loop (monitor)                          │
│    - aiogram polling (bot commands + callbacks)             │
└────────────────────────────────────────────────────────────┘

Tech канал:
┌──────────────────────────────────────────────────┐
│  [Видео пересланное без автора]                  │
│                                                   │
│  📹 Канал: @source_channel                        │
│  ⏱ 120с | 📦 45MB                                │
│                                                   │
│  [✅ Approve]  [❌ Reject]                        │
└──────────────────────────────────────────────────┘
```

**Поток модерации:**
1. Monitor (Stage 2a) пересылает видео в Tech + шлёт инфо-сообщение
2. **Этот Stage:** Bot отправляет кнопки Approve/Reject к инфо-сообщению
3. Админ нажимает Approve → db.update_video_status(video_id, VideoStatus.APPROVED) + db.add_job(DOWNLOAD)
4. Админ нажимает Reject → db.update_video_status(video_id, VideoStatus.REJECTED)

**Интеграция с Monitor:**
Monitor из Stage 2a отправляет инфо-сообщение через tg_client.send_message(). Нужно изменить: вместо send_message использовать aiogram bot для отправки инфо + кнопок вместе. Для этого Monitor должен получить ссылку на aiogram Bot (или callback).

**Решение:** Monitor вызывает callback-функцию после пересылки. __main__.py передаёт эту функцию при создании Monitor:

```python
# В __main__.py:
async def on_new_video(video_id: int, tech_message_ids: list[int]):
    """Callback: Monitor переслал видео в Tech, теперь отправить кнопки."""
    video = await db.get_video(video_id)
    keyboard = get_moderation_keyboard(video_id)
    info_text = format_video_info(video)
    await aiogram_bot.send_message(config.tech_channel_id, info_text, reply_markup=keyboard)

monitor = TelegramMonitor(config, db, tg_client, on_new_video=on_new_video)
```

---

## Модуль 1: `src/video_clipper/bot/keyboards.py`

```python
"""Клавиатуры Telegram-бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_moderation_keyboard(video_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура модерации: Approve / Reject.

    Callback data format:
      - "approve:{video_id}"
      - "reject:{video_id}"
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve:{video_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject:{video_id}"),
        ]
    ])


def format_video_info(video: dict) -> str:
    """
    Форматировать инфо о видео для отправки в Tech канал.

    Формат:
      📹 Канал: {source_title или chat_id}
      ⏱ {duration}с | 📦 {size_mb}MB
      🆔 video #{video_id}
    """
    duration = video.get("duration", 0)
    size_bytes = video.get("file_size", 0)
    size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else 0
    chat_id = video.get("source_chat_id", "?")
    video_id = video.get("id", "?")

    return (
        f"📹 Канал: <code>{chat_id}</code>\n"
        f"⏱ {duration}с | 📦 {size_mb}MB\n"
        f"🆔 video #{video_id}"
    )
```

## Модуль 2: `src/video_clipper/bot/moderation.py`

```python
"""Обработчики модерации: Approve/Reject inline-кнопки."""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery

from video_clipper.constants import VideoStatus, JobType
from video_clipper.database import Database

logger = logging.getLogger(__name__)

router = Router()

# Модуль-уровень переменные (устанавливаются через setup())
_db: Database | None = None
_admin_id: int = 0


def setup(db: Database, admin_id: int) -> None:
    """Инициализация модуля с зависимостями (DI)."""
    global _db, _admin_id
    _db = db
    _admin_id = admin_id


@router.callback_query(lambda c: c.data and c.data.startswith("approve:"))
async def handle_approve(callback: CallbackQuery) -> None:
    """
    Обработчик кнопки Approve.

    Реализация — смотри TGF: handlers/moderation/callbacks.py:
    1. Проверить что callback.from_user.id == _admin_id
    2. Извлечь video_id из callback.data ("approve:{video_id}")
    3. await _db.update_video_status(video_id, VideoStatus.APPROVED)
    4. await _db.add_job(job_type=JobType.DOWNLOAD, video_id=video_id)
    5. Обновить сообщение: "✅ Approved by admin | video #{video_id}"
    6. Убрать клавиатуру (reply_markup=None)
    7. await callback.answer("Approved")
    8. Логировать: "Video {video_id} approved"
    """


@router.callback_query(lambda c: c.data and c.data.startswith("reject:"))
async def handle_reject(callback: CallbackQuery) -> None:
    """
    Обработчик кнопки Reject.

    1. Проверить admin
    2. Извлечь video_id
    3. await _db.update_video_status(video_id, VideoStatus.REJECTED)
    4. Обновить сообщение: "❌ Rejected by admin | video #{video_id}"
    5. Убрать клавиатуру
    6. await callback.answer("Rejected")
    7. Логировать: "Video {video_id} rejected"
    """
```

## Модуль 3: `src/video_clipper/bot/handlers.py`

```python
"""Команды Telegram-бота: /start, /status, /sources, /add_source, /remove_source."""

import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from video_clipper.database import Database
from video_clipper.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

router = Router()

# Модуль-уровень переменные (устанавливаются через setup())
_db: Database | None = None
_tg_client: TelegramClientWrapper | None = None
_admin_id: int = 0


def setup(db: Database, tg_client: TelegramClientWrapper, admin_id: int) -> None:
    """Инициализация модуля с зависимостями."""
    global _db, _tg_client, _admin_id
    _db = db
    _tg_client = tg_client
    _admin_id = admin_id


def _is_admin(message: Message) -> bool:
    """Проверка что сообщение от админа."""
    return message.from_user and message.from_user.id == _admin_id


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """
    /start — приветствие.
    Если не админ → "Нет доступа"
    Если админ → "Video Clipper Bot v0.1.0 | /help для списка команд"
    """


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """
    /help — список команд.
    Вывести:
      /sources — список каналов-источников
      /add_source <ID|URL|@username> — добавить источник
      /remove_source <ID> — удалить источник
      /status — статус системы
    """


@router.message(Command("sources"))
async def cmd_sources(message: Message) -> None:
    """
    /sources — список активных каналов-источников.
    Реализация — смотри TGF: handlers/sources/ для формата вывода.
    Использует db.get_active_sources().
    Формат: нумерованный список с chat_id, title, video_count.
    """


@router.message(Command("add_source"))
async def cmd_add_source(message: Message) -> None:
    """
    /add_source — добавить канал-источник.

    Реализация — смотри TGF: handlers/sources/add.py (строки 29-156).
    Адаптировать под нашу архитектуру.

    Поддерживаемые форматы ввода:
    1. По ID: /add_source -1001234567890
    2. По URL: /add_source https://t.me/channel_name
    3. По username: /add_source @channel_name или /add_source channel_name
    4. По пересланному сообщению: переслать любое сообщение из канала боту

    Алгоритм:
    1. Проверить _is_admin(message)
    2. Если message.forward_from_chat → chat_id из forward
    3. Иначе: парсить args
       - Попробовать int(input_value) → chat_id
       - Попробовать parse_telegram_link(input_value) → username
       - await _tg_client.get_entity(username) → chat_id
    4. await _db.add_source(chat_id, chat_title, chat_username)
    5. Ответить: "✅ Источник добавлен: {title} ({chat_id})"

    ВАЖНО: после добавления источника Monitor должен перезагрузить фильтр каналов.
    Для MVP: логировать "Source added, restart to apply" (полная reload в будущем).
    """


@router.message(Command("remove_source"))
async def cmd_remove_source(message: Message) -> None:
    """
    /remove_source <chat_id> — удалить источник.
    Только по chat_id (числовой).
    """


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """
    /status — статус системы.
    Показать:
      - Кол-во активных источников
      - Кол-во видео по статусам (queued, downloading, etc.)
      - Кол-во jobs в очереди
    Использует SQL COUNT GROUP BY.
    """
```

### Парсинг Telegram-ссылок

Добавить утилиту (можно прямо в handlers.py как приватную функцию):

```python
import re

def _parse_telegram_link(text: str) -> str | None:
    """
    Извлечь username из Telegram-ссылки.
    Поддерживает:
      - https://t.me/channel_name → channel_name
      - @channel_name → channel_name
      - channel_name → channel_name
    Возвращает username без @ или None.
    """
    text = text.strip()

    # https://t.me/channel_name или https://t.me/+invite
    match = re.match(r'https?://t\.me/(?:\+)?(\w+)', text)
    if match:
        return match.group(1)

    # @channel_name
    if text.startswith('@'):
        return text[1:]

    # Просто username
    if re.match(r'^[a-zA-Z]\w{3,}$', text):
        return text

    return None
```

---

## Изменения в существующих файлах

### 1. `src/video_clipper/bot/__init__.py` — ОБНОВИТЬ

```python
"""Telegram-бот: команды и модерация."""
from video_clipper.bot.handlers import router as handlers_router
from video_clipper.bot.moderation import router as moderation_router

__all__ = ["handlers_router", "moderation_router"]
```

### 2. `src/video_clipper/pipeline/monitor.py` — МОДИФИКАЦИЯ

Добавить callback для уведомления о новом видео. Monitor не знает про aiogram (Правило 4 + 5), но может вызвать callback:

```python
class TelegramMonitor:
    def __init__(
        self,
        config: Config,
        db: Database,
        tg_client: TelegramClientWrapper,
        on_new_video: Callable | None = None,  # НОВЫЙ параметр
    ) -> None:
        # ... существующий код ...
        self._on_new_video = on_new_video  # callback(video_id, buffer_msg_ids, tech_msg_ids)
```

В `_process_single()` после пересылки и db.add_video():
```python
# После успешной пересылки и записи в БД:
if self._on_new_video:
    await self._on_new_video(video_id)
```

### 3. `src/video_clipper/database/models.py` — ДОБАВИТЬ методы

```python
# ------------------------------------------------------------------
# Sources (дополнительные методы)
# ------------------------------------------------------------------

async def remove_source(self, chat_id: int) -> bool:
    """Удалить канал-источник. Возвращает True если удалён."""
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            "DELETE FROM sources WHERE chat_id = ?", (chat_id,)
        )
        return cursor.rowcount > 0

async def increment_video_count(self, chat_id: int) -> None:
    """Увеличить счётчик видео для канала-источника."""
    async with self._get_connection() as conn:
        await conn.execute(
            "UPDATE sources SET video_count = video_count + 1 WHERE chat_id = ?",
            (chat_id,),
        )

# ------------------------------------------------------------------
# Videos (дополнительные методы для Stage 2b)
# ------------------------------------------------------------------

async def get_video_counts_by_status(self) -> dict[str, int]:
    """Количество видео по статусам. Для /status команды."""
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
        )
        rows = await cursor.fetchall()
        return {row["status"]: row["cnt"] for row in rows}

async def get_pending_jobs_count(self) -> int:
    """Количество задач в очереди (status=queued)."""
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'queued'"
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0
```

### 4. `src/video_clipper/__main__.py` — ОБНОВИТЬ

Добавить инициализацию aiogram и параллельный запуск:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from video_clipper.config import load_config
from video_clipper.database import Database
from video_clipper.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main():
    config = load_config()
    setup_logging()
    # ... баннер, БД ...

    # TelegramClientWrapper (Stage 2a)
    from video_clipper.services.telegram_client import TelegramClientWrapper
    tg_client = TelegramClientWrapper(config)

    if not config.mock_monitor:
        await tg_client.connect()

    # Aiogram Bot (Stage 2b)
    from video_clipper.bot.keyboards import get_moderation_keyboard, format_video_info
    from video_clipper.bot import moderation, handlers

    aiogram_bot = None
    dp = None

    if not config.mock_monitor and config.bot_token:
        aiogram_bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        dp = Dispatcher()

        # Setup DI
        moderation.setup(db, config.admin_id)
        handlers.setup(db, tg_client, config.admin_id)

        # Include routers
        dp.include_router(handlers.router)
        dp.include_router(moderation.router)

        logger.info("Aiogram bot initialized")

    # Callback для Monitor → отправить кнопки модерации
    async def on_new_video(video_id: int) -> None:
        """Monitor переслал видео → отправить кнопки в Tech."""
        if aiogram_bot is None:
            return
        video = await db.get_video(video_id)
        if video is None:
            return
        keyboard = get_moderation_keyboard(video_id)
        info_text = format_video_info(video)
        msg = await aiogram_bot.send_message(
            config.tech_channel_id, info_text, reply_markup=keyboard,
        )
        # Сохранить message_id кнопок для возможного обновления
        # (пока просто логируем)
        logger.debug(f"Moderation keyboard sent for video {video_id}")

    # Monitor (Stage 2a) с callback
    from video_clipper.pipeline.monitor import TelegramMonitor
    monitor = TelegramMonitor(config, db, tg_client, on_new_video=on_new_video)
    await monitor.start()

    # Запуск
    logger.info("All modules loaded. System ready.")

    try:
        if config.mock_monitor:
            await asyncio.Event().wait()
        elif dp and aiogram_bot:
            # Параллельно: Telethon + aiogram
            # Telethon уже слушает через registered handlers
            # aiogram нужен для polling
            await dp.start_polling(
                aiogram_bot,
                allowed_updates=["message", "callback_query"],
            )
        else:
            await tg_client.client.run_until_disconnected()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await monitor.stop()
        if not config.mock_monitor:
            await tg_client.disconnect()
        if aiogram_bot:
            await aiogram_bot.session.close()
        await db.close()
        logger.info("Shutdown complete.")
```

**ВАЖНО:** Telethon и aiogram работают в одном event loop. Telethon регистрирует хэндлеры, aiogram использует long polling. Оба работают параллельно через asyncio.

---

## Тесты

### Файл: `tests/test_stage2b.py`

```python
"""Тесты для Stage 2b: Bot + Модерация + Команды."""

import pytest
import pytest_asyncio

from video_clipper.config import Config
from video_clipper.database import Database
from video_clipper.constants import VideoStatus, JobType


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init_tables()
    yield database
    await database.close()


# ─────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────

class TestKeyboards:

    def test_moderation_keyboard(self):
        """Клавиатура модерации содержит Approve и Reject."""
        from video_clipper.bot.keyboards import get_moderation_keyboard
        kb = get_moderation_keyboard(42)
        buttons = kb.inline_keyboard[0]
        assert len(buttons) == 2
        assert buttons[0].callback_data == "approve:42"
        assert buttons[1].callback_data == "reject:42"

    def test_format_video_info(self):
        """Форматирование инфо о видео."""
        from video_clipper.bot.keyboards import format_video_info
        video = {
            "id": 1,
            "source_chat_id": -1001234567890,
            "duration": 120,
            "file_size": 50 * 1024 * 1024,
        }
        text = format_video_info(video)
        assert "120" in text
        assert "#1" in text

    def test_format_video_info_no_size(self):
        """Форматирование без размера файла."""
        from video_clipper.bot.keyboards import format_video_info
        video = {"id": 2, "source_chat_id": -100, "duration": 60, "file_size": 0}
        text = format_video_info(video)
        assert "60" in text


# ─────────────────────────────────────────────────────
# Database — новые методы
# ─────────────────────────────────────────────────────

class TestDatabaseNewMethods:

    async def test_remove_source(self, db):
        """Удаление источника."""
        await db.add_source(-1001111111111, "Test Channel")
        result = await db.remove_source(-1001111111111)
        assert result is True
        sources = await db.get_active_sources()
        assert len(sources) == 0

    async def test_remove_source_nonexistent(self, db):
        """Удаление несуществующего источника."""
        result = await db.remove_source(-9999)
        assert result is False

    async def test_increment_video_count(self, db):
        """Инкремент счётчика видео."""
        await db.add_source(-1001111111111, "Test")
        await db.increment_video_count(-1001111111111)
        await db.increment_video_count(-1001111111111)
        sources = await db.get_active_sources()
        assert sources[0]["video_count"] == 2

    async def test_get_video_counts_by_status(self, db):
        """Подсчёт видео по статусам."""
        await db.add_video(-100, 1, duration=60)
        await db.add_video(-100, 2, duration=120)
        video_id = await db.add_video(-100, 3, duration=90)
        await db.update_video_status(video_id, VideoStatus.DOWNLOADED)

        counts = await db.get_video_counts_by_status()
        assert counts.get("queued", 0) == 2
        assert counts.get("downloaded", 0) == 1

    async def test_get_pending_jobs_count(self, db):
        """Количество задач в очереди."""
        count = await db.get_pending_jobs_count()
        assert count == 0

        await db.add_job(job_type=JobType.DOWNLOAD, video_id=1)
        await db.add_job(job_type=JobType.DOWNLOAD, video_id=2)
        count = await db.get_pending_jobs_count()
        assert count == 2


# ─────────────────────────────────────────────────────
# Handlers — parse_telegram_link
# ─────────────────────────────────────────────────────

class TestParseTelegramLink:

    def test_https_link(self):
        from video_clipper.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("https://t.me/channel_name") == "channel_name"

    def test_at_username(self):
        from video_clipper.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("@channel_name") == "channel_name"

    def test_plain_username(self):
        from video_clipper.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("channel_name") == "channel_name"

    def test_invalid(self):
        from video_clipper.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("123") is None
        assert _parse_telegram_link("") is None
```

---

## Правила выполнения

1. **Пиши ТОЛЬКО код.** Не объясняй, не задавай вопросов.
2. **Прочитай ВСЕ указанные файлы** перед началом.
3. **Изучи TGF-файлы** и адаптируй паттерны.
4. **Заполняй существующие заглушки** — bot/handlers.py, bot/moderation.py, bot/keyboards.py.
5. **Абсолютные импорты** (Правило 1).
6. **aiogram ТОЛЬКО в bot/** — pipeline/ не импортирует aiogram (Правило 4).
7. **Mock-режим:** если mock_monitor=True, бот не запускается (только заглушки грузятся).
8. Тесты: `python -m pytest tests/ -v`

## Порядок реализации

1. `bot/keyboards.py` — клавиатуры и форматирование
2. `bot/moderation.py` — callback handlers (Approve/Reject)
3. `bot/handlers.py` — команды (/start, /help, /sources, /add_source, /remove_source, /status)
4. `bot/__init__.py` — реэкспорт роутеров
5. `database/models.py` — новые методы (remove_source, increment_video_count, counts)
6. `pipeline/monitor.py` — добавить on_new_video callback
7. `__main__.py` — добавить aiogram Bot + Dispatcher + параллельный запуск
8. `tests/test_stage2b.py` — тесты
9. Запустить все тесты

## Критерии приёмки

### Код:
1. `bot/keyboards.py` — get_moderation_keyboard() + format_video_info()
2. `bot/moderation.py` — Approve/Reject callback handlers с проверкой админа
3. `bot/handlers.py` — /start, /help, /sources, /add_source (ID/URL/@/forward), /remove_source, /status
4. `bot/__init__.py` — реэкспорт роутеров
5. `database/models.py` — remove_source, increment_video_count, get_video_counts_by_status, get_pending_jobs_count
6. `pipeline/monitor.py` — on_new_video callback
7. `__main__.py` — aiogram Bot + Dispatcher параллельно с Telethon

### Тесты:
8. `tests/test_stage2b.py` — все тесты проходят
9. Существующие тесты — НЕ сломаны
10. `python -m pytest tests/ -v` — all passed

### Запуск:
11. Mock-режим стартует без ошибок
12. Все модули загружаются

### Архитектура:
13. `import aiogram` только в `bot/` (нигде в pipeline/ или services/)
14. Monitor использует callback, не знает про aiogram
15. Все импорты абсолютные
