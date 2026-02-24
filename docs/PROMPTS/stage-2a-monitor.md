# ЗАДАНИЕ: Этап 2a — TelegramClient + Monitor (Source → Buffer → Tech)

## Роль
Ты — исполнитель. Архитектор утвердил требования. Твоя задача — реализовать Telethon-обёртку и мониторинг каналов с пересылкой по цепочке Source → Buffer → Tech. Заглушки уже созданы — ты заполняешь их реальным кодом.

## Проект
- Путь: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr/`
- Ветка: `stage-2/monitor-downloader` (ты на ней)
- Среда: macOS, Python 3.13, venv в `.venv/`
- Запуск: `python -m slicr`

## Обязательно прочитай перед началом

### Проект slicr:
1. `docs/CLAUDE.md` — правила проекта, архитектура, правила импортов
2. `docs/MODULE_MAP.md` — карта модулей, утверждённая структура
3. `src/slicr/config.py` — текущий конфиг (будешь расширять)
4. `src/slicr/constants.py` — enum-ы статусов
5. `src/slicr/database/models.py` — все CRUD-методы БД
6. `src/slicr/database/connection.py` — ConnectionMixin
7. `creds.example.json` — шаблон конфига (будешь расширять)
8. Текущие заглушки: `pipeline/monitor.py`, `services/telegram_client.py`
9. `src/slicr/__main__.py` — точка входа (будешь обновлять)
10. `tests/conftest.py` — существующие фикстуры

### Референс — TGForwardez (ИЗУЧИ и АДАПТИРУЙ):
| Что взять | Файл TGF | Как адаптировать |
|-----------|----------|------------------|
| Инициализация Telethon: StringSession vs файл, client.start(), try/except EOFError | `/Users/dvofis/Desktop/Програмирование/TGForwardez/bot.py` (строки ~72-78, ~187) | → `services/telegram_client.py` — добавить прокси, обернуть в класс |
| Event handler: `@client.on(events.NewMessage())`, пересылка Source→Buffer→Tech | `/Users/dvofis/Desktop/Програмирование/TGForwardez/handlers/forwarding.py` | → `pipeline/monitor.py` — добавить фильтрацию видео, текст-фильтр |
| Media group handling: cache + timeout для альбомов | `/Users/dvofis/Desktop/Програмирование/TGForwardez/handlers/forwarding.py` (media_group_cache) | → `pipeline/monitor.py` — перенести логику альбомов |
| Конфиг: session_string, api_id/hash из JSON | `/Users/dvofis/Desktop/Програмирование/TGForwardez/config_loader.py` | → `config.py` — паттерн загрузки |
| Генерация session string (QR / SMS) | `/Users/dvofis/Desktop/Програмирование/TGForwardez/scripts/generate_session_string.py` | → `scripts/generate_session.py` — скопировать и адаптировать |

**ВАЖНО:**
- Бери **паттерны и логику**, не копируй слепо — у нас другая архитектура
- В TGF Telethon используется напрямую в handlers/ — у нас он изолирован в `services/` (Правило 4)
- В TGF нет прокси и нет фильтрации по видео — это наши новые требования

---

## Архитектура потока

```
Source каналы (20+)
     │
     │ events.NewMessage → _handle_new_message()
     ▼
┌─────────────────────────────┐
│  Фильтрация:                │
│  1. Есть видео?             │
│  2. duration 30-7200 сек    │
│  3. size <= max_file_size   │
│  4. Текст: whitelist/       │
│     blacklist (если задан)  │
│  5. Не дубликат?            │
│  6. Альбом? → собрать       │
└──────────┬──────────────────┘
           │ прошло фильтры
           ▼
┌──────────────────────────────────────────────────────────────┐
│  1. forward_messages → Buffer канал (с автором)              │
│  2. forward_messages → Tech канал (drop_author=True)         │
│  3. db.add_video() — запись в БД (status=queued)             │
│  4. Отправить инфо-сообщение в Tech (канал, dur, size)       │
│     (кнопки Approve/Reject будут в Stage 2b через aiogram)   │
└──────────────────────────────────────────────────────────────┘
```

**Stage 2a НЕ включает:**
- Кнопки Approve/Reject (это Stage 2b — aiogram bot)
- Скачивание видео (это Stage 2c — downloader)
- Бот-команды /add_source (это Stage 2b)

**Stage 2a включает:**
- TelegramClientWrapper (services/) — Telethon обёртка
- TelegramMonitor (pipeline/) — мониторинг + пересылка
- Обновление config.py, creds.example.json, __main__.py
- Скрипт generate_session.py

---

## Модуль 1: `src/slicr/services/telegram_client.py`

### Ответственность
Изоляция Telethon от остального кода (Правило 4). Один экземпляр на всё приложение. Создаётся в `__main__.py`, передаётся через DI (Dependency Injection).

### Класс: TelegramClientWrapper

```python
import logging
from typing import Callable

from slicr.config import Config

logger = logging.getLogger(__name__)


class TelegramClientWrapper:
    """
    Обёртка над Telethon: подключение, прокси, пересылка, скачивание.
    Единственное место в проекте, где импортируется telethon.
    """

    def __init__(self, config: Config) -> None:
        """
        Создаёт Telethon-клиент (НЕ подключается).

        Session:
        - Если config.session_string задан — StringSession
        - Иначе — файловая сессия "slicr" (создаст slicr.session)

        Proxy:
        - config.proxy = None → прямое подключение
        - config.proxy = {"type": "socks5", "host": "...", "port": ..., ...}
        - config.proxy = {"type": "mtproto", "host": "...", "port": ..., "secret": "..."}

        Реализация — смотри TGF: bot.py строки ~72-78, адаптируй.
        Добавь proxy= параметр в TelegramClient().
        """

    async def connect(self) -> None:
        """
        Подключиться к Telegram.

        Реализация — смотри TGF: bot.py строки ~187:
        - try: await client.start()
        - except EOFError: raise RuntimeError с подсказкой запустить generate_session.py
        - me = await client.get_me()
        - Логировать: "Telethon authorized as: {name} (@{username})"
        """

    async def disconnect(self) -> None:
        """Отключиться от Telegram."""

    @property
    def client(self):
        """
        Прямой доступ к Telethon-клиенту.
        Нужен для monitor.py — регистрации хэндлеров через on_new_message().
        Тип: telethon.TelegramClient (но в type hint — Any, чтобы не нарушать изоляцию).
        """

    def on_new_message(self, chats: list[int] | None = None):
        """
        Декоратор для регистрации хэндлера на новые сообщения.
        Обёртка над @client.on(events.NewMessage(chats=chats)).

        Использование в monitor.py:
            @tg_client.on_new_message(chats=source_ids)
            async def handler(event):
                ...

        Это позволяет monitor.py НЕ импортировать telethon (Правило 4).
        """

    async def forward_messages(
        self,
        to_chat_id: int,
        from_chat_id: int,
        message_ids: list[int],
        drop_author: bool = False,
    ) -> list:
        """
        Переслать сообщения из одного чата в другой.

        Реализация — смотри TGF: handlers/forwarding.py:
        - client.forward_messages(entity=to_chat_id, messages=message_ids,
                                   from_peer=from_chat_id, drop_author=drop_author)

        Возвращает список отправленных сообщений.
        """

    async def send_message(self, chat_id: int, text: str) -> None:
        """Отправить текстовое сообщение (для инфо в Tech канал)."""

    async def download_media(
        self,
        message,
        file_path: str,
        progress_callback: Callable | None = None,
    ) -> str | None:
        """
        Скачать медиа из сообщения (будет использоваться в Stage 2c).
        Обернуть в retry с exponential backoff (3 попытки).

        - progress_callback(current_bytes, total_bytes)
        - Возвращает путь к файлу или None при ошибке
        """

    async def get_entity(self, entity_id: int):
        """Получить entity по ID (для валидации каналов)."""

    async def get_messages(self, chat_id: int, ids: list[int]):
        """Получить конкретные сообщения по ID."""
```

### Прокси — реализация

```python
# В __init__:
from telethon import TelegramClient
from telethon.sessions import StringSession

# Session
if config.session_string:
    session = StringSession(config.session_string)
else:
    session = "slicr"  # файл slicr.session

# Proxy
proxy = None
connection = None  # для MTProxy

if config.proxy:
    proxy_type = config.proxy.get("type", "")

    if proxy_type == "socks5":
        import socks
        proxy = (
            socks.SOCKS5,
            config.proxy["host"],
            config.proxy["port"],
            True,  # rdns
            config.proxy.get("username"),
            config.proxy.get("password"),
        )

    elif proxy_type == "mtproto":
        from telethon.network import connection as tl_conn
        connection = tl_conn.ConnectionTcpMTProxyRandomizedIntermediate
        proxy = (
            config.proxy["host"],
            config.proxy["port"],
            config.proxy["secret"],
        )

# Клиент
kwargs = {"proxy": proxy} if proxy else {}
if connection:
    kwargs["connection"] = connection

self._client = TelegramClient(session, config.api_id, config.api_hash, **kwargs)
```

### Retry для download_media

```python
import asyncio

async def download_media(self, message, file_path, progress_callback=None):
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            result = await self._client.download_media(
                message, file=file_path, progress_callback=progress_callback
            )
            return result
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"Download failed after {max_retries} attempts: {e}")
                return None
            wait = 2 ** attempt  # 2, 4, 8 секунд
            logger.warning(f"Download attempt {attempt} failed, retrying in {wait}s: {e}")
            await asyncio.sleep(wait)
```

---

## Модуль 2: `src/slicr/pipeline/monitor.py`

### Ответственность
Слушает Telegram-каналы в реальном времени. При получении подходящего видео:
1. Пересылает Source → Buffer (с автором)
2. Пересылает Source → Tech (без автора)
3. Отправляет инфо-сообщение в Tech
4. Создаёт запись в БД

### Класс: TelegramMonitor

```python
import asyncio
import logging
from slicr.config import Config
from slicr.constants import VideoStatus
from slicr.database import Database
from slicr.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

# Таймаут для сбора альбома (смотри TGF: handlers/forwarding.py)
MEDIA_GROUP_TIMEOUT = 1.0  # секунд


class TelegramMonitor:
    """Мониторинг Telegram-каналов: фильтрация видео + пересылка Source→Buffer→Tech."""

    def __init__(self, config: Config, db: Database, tg_client: TelegramClientWrapper) -> None:
        self.config = config
        self.db = db
        self.tg_client = tg_client
        self._running = False
        # Кэш для сбора медиа-альбомов (как в TGF)
        self._media_group_cache: dict[int, list] = {}
        self._media_group_tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        """
        Начать мониторинг.

        Если config.mock_monitor == True:
          - Логировать "TelegramMonitor running in MOCK mode"
          - return (не регистрировать хэндлеры)

        Иначе:
          1. await self._sync_sources() — синхронизировать config.source_channels с БД
          2. Загрузить source_ids из db.get_active_sources()
          3. Если source_ids пустой — логировать warning и return
          4. Зарегистрировать хэндлер:
               @tg_client.on_new_message(chats=source_ids)
               async def handler(event):
                   await self._handle_new_message(event)
          5. self._running = True
          6. Логировать: "Monitoring {N} channels"
        """

    async def stop(self) -> None:
        """Остановить мониторинг."""
        self._running = False
        # Отменить все pending задачи альбомов
        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_cache.clear()
        self._media_group_tasks.clear()
        logger.info("TelegramMonitor stopped")

    async def _handle_new_message(self, event) -> None:
        """
        Обработчик нового сообщения из канала-источника.

        Альбомы (смотри TGF: handlers/forwarding.py, media_group_cache):
          - Если event.message.grouped_id is not None:
              - Добавить в _media_group_cache[grouped_id]
              - Отменить старый таск если есть
              - Создать новый таск с таймаутом MEDIA_GROUP_TIMEOUT
              - Таск вызывает _process_album(grouped_id)
          - Иначе: обработать как одиночное сообщение → _process_single(event)
        """

    async def _process_single(self, event) -> None:
        """
        Обработка одиночного сообщения (не альбом).

        Фильтры (проверять по порядку):
        1. event.message.video is not None (именно video, не document/gif)
        2. Получить атрибуты видео (см. ниже)
        3. duration >= config.min_video_duration (30 сек)
        4. duration <= config.max_video_duration (7200 сек)
        5. file_size <= config.max_file_size (2 GB)
        6. _check_text_filter(caption) — whitelist/blacklist
        7. not await db.is_duplicate(chat_id, message_id)

        Если все пройдены:
        1. Переслать в Buffer: await tg_client.forward_messages(
               to_chat_id=config.buffer_channel_id,
               from_chat_id=chat_id,
               message_ids=[message_id],
               drop_author=False)
        2. Переслать в Tech: await tg_client.forward_messages(
               to_chat_id=config.tech_channel_id,
               from_chat_id=chat_id,
               message_ids=[message_id],
               drop_author=True)
        3. Отправить инфо в Tech: await tg_client.send_message(
               config.tech_channel_id,
               f"📹 Канал: {source_title}\n⏱ {duration}с | 📦 {size_mb}MB")
        4. Сохранить в БД: video_id = await db.add_video(...)
        5. Логировать: "New video: chat={chat_id} msg={msg_id} dur={duration}s size={size_mb}MB"

        Если фильтр не пройден — debug-лог с причиной.
        """

    async def _process_album(self, grouped_id: int) -> None:
        """
        Обработка альбома (медиа-группы).

        Логика — адаптация из TGF (handlers/forwarding.py):
        1. events = self._media_group_cache.pop(grouped_id, [])
        2. Отфильтровать: оставить только events с видео, прошедшие фильтры
        3. Если есть подходящие видео:
           - Переслать ВСЮ группу (все message_ids) в Buffer с автором
           - Переслать ВСЮ группу в Tech без автора
           - Отправить инфо в Tech: "📹 Альбом ({N} видео) | Канал: {title}"
           - Для каждого видео из альбома: db.add_video()
        4. Очистить _media_group_tasks[grouped_id]
        """

    def _check_text_filter(self, caption: str | None) -> bool:
        """
        Проверка текста по whitelist/blacklist.

        - Если config.filter_keywords не пустой:
            caption должен содержать хотя бы одно ключевое слово (регистронезависимо)
        - Если config.filter_stopwords не пустой:
            caption НЕ должен содержать стоп-слова
        - Если оба пустые — пропускаем всё (no filter)
        - Если caption is None — считаем пустой строкой

        return True если пост проходит фильтр
        """

    async def _sync_sources(self) -> None:
        """
        Синхронизирует config.source_channels с БД.
        Для каждого chat_id из конфига: await db.add_source(chat_id)
        (add_source использует INSERT OR IGNORE — дубли безопасны)
        """
```

### Получение video-атрибутов из Telethon

```python
# В _process_single():
video = event.message.video
if video is None:
    logger.debug(f"Skipped msg {event.message.id}: no video")
    return

# Атрибуты видео
from telethon.tl.types import DocumentAttributeVideo  # импорт ТОЛЬКО в telegram_client.py!

# СТОП! Мы в pipeline/monitor.py — нельзя импортировать telethon напрямую (Правило 4).
# Решение: добавить метод в TelegramClientWrapper:
```

**Добавить в TelegramClientWrapper:**

```python
@staticmethod
def extract_video_info(message) -> dict | None:
    """
    Извлечь информацию о видео из Telethon message.
    Возвращает dict с ключами: duration, width, height, file_size
    Или None если сообщение не содержит видео.
    """
    from telethon.tl.types import DocumentAttributeVideo

    video = message.video
    if video is None:
        return None

    duration = 0
    width = 0
    height = 0

    for attr in video.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            duration = attr.duration
            width = attr.w
            height = attr.h
            break

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "file_size": video.size or 0,
    }
```

Тогда в monitor.py:
```python
video_info = TelegramClientWrapper.extract_video_info(event.message)
if video_info is None:
    return
```

### Mock-режим
Если `config.mock_monitor == True`:
- `start()` логирует "TelegramMonitor running in MOCK mode" и возвращается
- Не регистрирует хэндлеры, не обращается к Telethon

---

## Изменения в существующих файлах

### 1. `src/slicr/config.py` — РАСШИРИТЬ

Добавить новые поля в dataclass `Config`:

```python
@dataclass
class Config:
    # ... (все существующие поля остаются БЕЗ ИЗМЕНЕНИЙ)

    # Telegram каналы (НОВОЕ)
    buffer_channel_id: int = 0
    # Канал-буфер: хранилище пересланных видео

    # Proxy (НОВОЕ)
    proxy: dict | None = None
    # Формат: {"type": "socks5", "host": "...", "port": 1080, "username": "...", "password": "..."}
    # Или:    {"type": "mtproto", "host": "...", "port": ..., "secret": "..."}
    # Или None — прямое подключение

    # Session (НОВОЕ)
    session_string: str = ""
    # StringSession для Telethon (альтернатива файловой сессии)

    # Download (НОВОЕ — понадобится в Stage 2c, но добавляем сейчас)
    max_concurrent_downloads: int = 1
    max_file_size: int = 2 * 1024 * 1024 * 1024  # 2 GB

    # Cleanup (НОВОЕ — понадобится в Stage 2c)
    cleanup_enabled: bool = True
    cleanup_after_hours: int = 48

    # Text filter (НОВОЕ)
    filter_keywords: list[str] = field(default_factory=list)
    # Whitelist: если не пустой, caption должен содержать хотя бы одно слово
    filter_stopwords: list[str] = field(default_factory=list)
    # Blacklist: если caption содержит стоп-слово — пропускаем
```

В `load_config()` добавить парсинг:

```python
config = Config(
    # ... все существующие поля без изменений ...
    buffer_channel_id=int(data.get("buffer_channel_id", 0)),
    proxy=data.get("proxy", None),
    session_string=data.get("session_string", ""),
    max_concurrent_downloads=int(data.get("max_concurrent_downloads", 1)),
    max_file_size=int(data.get("max_file_size", 2 * 1024 * 1024 * 1024)),
    cleanup_enabled=bool(data.get("cleanup_enabled", True)),
    cleanup_after_hours=int(data.get("cleanup_after_hours", 48)),
    filter_keywords=list(data.get("filter_keywords", [])),
    filter_stopwords=list(data.get("filter_stopwords", [])),
)
```

### 2. `creds.example.json` — РАСШИРИТЬ

```json
{
    "api_id": 0,
    "api_hash": "YOUR_API_HASH",
    "bot_token": "YOUR_BOT_TOKEN",
    "admin_id": 0,
    "tech_channel_id": 0,
    "target_channel_id": 0,
    "buffer_channel_id": 0,

    "session_string": "",

    "proxy": null,
    "_proxy_socks5_example": {
        "type": "socks5",
        "host": "1.2.3.4",
        "port": 1080,
        "username": "user",
        "password": "pass"
    },
    "_proxy_mtproto_example": {
        "type": "mtproto",
        "host": "1.2.3.4",
        "port": 443,
        "secret": "dd..."
    },

    "claude_api_key": "sk-ant-YOUR_KEY",
    "claude_model": "claude-sonnet-4-20250514",

    "vk_access_token": "YOUR_VK_TOKEN",
    "vk_group_id": 0,

    "source_channels": [],

    "max_concurrent_downloads": 1,
    "max_file_size": 2147483648,

    "cleanup_enabled": true,
    "cleanup_after_hours": 48,

    "filter_keywords": [],
    "filter_stopwords": [],

    "dev_mode": true,
    "mock_gpu": true,
    "mock_selector": true,
    "mock_monitor": true
}
```

### 3. `src/slicr/__main__.py` — ОБНОВИТЬ

```python
async def main():
    # 1-5: (БЕЗ ИЗМЕНЕНИЙ — загрузка конфига, логирование, баннер, БД)

    # 6. Инициализировать Telegram-клиент (DI: создаём здесь, передаём всем)
    from slicr.services.telegram_client import TelegramClientWrapper

    tg_client = TelegramClientWrapper(config)

    if not config.mock_monitor:
        await tg_client.connect()
        logger.info("Telegram client connected")
    else:
        logger.info("Telegram client: MOCK mode (skipped)")

    # 7. Инициализировать Monitor
    from slicr.pipeline.monitor import TelegramMonitor

    monitor = TelegramMonitor(config, db, tg_client)
    await monitor.start()

    # 8. Импортировать остальные заглушки (проверка что грузятся)
    from slicr.pipeline.orchestrator import PipelineOrchestrator
    from slicr.pipeline.downloader import VideoDownloader
    from slicr.pipeline.transcriber import WhisperTranscriber
    from slicr.pipeline.selector import MomentSelector
    from slicr.pipeline.editor import VideoEditor
    from slicr.pipeline.publisher import ClipPublisher
    from slicr.gpu.guard import GPUGuard

    logger.info("All modules loaded")
    logger.info("Monitor active. Stages 2b-8: stubs.")

    # 9. Держим процесс (Telethon event loop)
    try:
        if not config.mock_monitor:
            # Telethon run_until_disconnected() вместо Event().wait()
            await tg_client.client.run_until_disconnected()
        else:
            await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await monitor.stop()
        if not config.mock_monitor:
            await tg_client.disconnect()
        await db.close()
        logger.info("Shutdown complete.")
```

### 4. `requirements.txt` — ДОБАВИТЬ

Добавить в секцию `# Telegram`:
```
pysocks>=1.7.1
```

### 5. `tests/conftest.py` — ОБНОВИТЬ фикстуру config

Добавить новые поля:
```python
@pytest.fixture
def config():
    return Config(
        # ... все существующие поля без изменений ...
        buffer_channel_id=0,
        proxy=None,
        session_string="",
        max_concurrent_downloads=1,
        max_file_size=2 * 1024 * 1024 * 1024,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        filter_keywords=[],
        filter_stopwords=[],
    )
```

---

## Новый файл: `scripts/generate_session.py`

Скопировать из TGF (`/Users/dvofis/Desktop/Програмирование/TGForwardez/scripts/generate_session_string.py`) и адаптировать:

- Изменить: загрузку api_id/api_hash из `creds.json` (наш формат)
- Изменить: имя сессии на "slicr"
- Оставить: оба метода аутентификации (QR + phone/SMS)
- Добавить: `chmod +x scripts/generate_session.py` после создания

---

## Новые тесты

### Файл: `tests/test_stage2a.py`

```python
"""Тесты для Stage 2a: TelegramClientWrapper + TelegramMonitor."""

import pytest
import pytest_asyncio

from slicr.config import Config
from slicr.database import Database
from slicr.constants import VideoStatus


# ─────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init_tables()
    yield database
    await database.close()


@pytest.fixture
def config(tmp_path):
    return Config(
        dev_mode=True,
        mock_gpu=True,
        mock_selector=True,
        mock_monitor=True,
        db_path=":memory:",
        api_id=12345,
        api_hash="test_hash",
        bot_token="test_token",
        admin_id=0,
        tech_channel_id=-1009999999999,
        target_channel_id=0,
        buffer_channel_id=-1008888888888,
        claude_api_key="test",
        vk_access_token="test",
        vk_group_id=0,
        source_channels=[-1001234567890],
        storage_base=str(tmp_path / "storage"),
        min_video_duration=30,
        max_video_duration=7200,
        max_file_size=2 * 1024 * 1024 * 1024,
        max_concurrent_downloads=1,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        proxy=None,
        session_string="",
        filter_keywords=[],
        filter_stopwords=[],
    )


# ─────────────────────────────────────────────────────
# TelegramClientWrapper
# ─────────────────────────────────────────────────────

class TestTelegramClientWrapper:

    def test_init_no_proxy(self, config):
        """Создание клиента без прокси."""
        from slicr.services.telegram_client import TelegramClientWrapper
        wrapper = TelegramClientWrapper(config)
        assert wrapper is not None
        assert wrapper.client is not None

    def test_init_session_string(self, config):
        """Создание клиента с session_string."""
        config.session_string = "1AbC2dEf3..."
        from slicr.services.telegram_client import TelegramClientWrapper
        wrapper = TelegramClientWrapper(config)
        assert wrapper is not None

    def test_init_socks5_proxy(self, config):
        """Создание клиента с SOCKS5 прокси."""
        config.proxy = {"type": "socks5", "host": "127.0.0.1", "port": 1080}
        from slicr.services.telegram_client import TelegramClientWrapper
        wrapper = TelegramClientWrapper(config)
        assert wrapper is not None

    def test_extract_video_info_none(self, config):
        """extract_video_info возвращает None для не-видео."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.video = None
        assert TelegramClientWrapper.extract_video_info(msg) is None


# ─────────────────────────────────────────────────────
# TelegramMonitor
# ─────────────────────────────────────────────────────

class TestTelegramMonitor:

    def test_init(self, config, db):
        """Инициализация монитора."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._running is False

    async def test_mock_start(self, config, db):
        """Mock-режим: start() не подключается к Telegram."""
        config.mock_monitor = True
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        await monitor.start()
        await monitor.stop()

    async def test_sync_sources(self, config, db):
        """Синхронизация source_channels из конфига в БД."""
        config.source_channels = [-1001111111111, -1002222222222]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        await monitor._sync_sources()
        sources = await db.get_active_sources()
        chat_ids = [s["chat_id"] for s in sources]
        assert -1001111111111 in chat_ids
        assert -1002222222222 in chat_ids

    def test_text_filter_no_filter(self, config, db):
        """Без фильтров — пропускает всё."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter(None) is True
        assert monitor._check_text_filter("любой текст") is True
        assert monitor._check_text_filter("") is True

    def test_text_filter_keywords(self, config, db):
        """Whitelist: пропускает только посты с ключевыми словами."""
        config.filter_keywords = ["подкаст", "интервью"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Новый подкаст с гостем") is True
        assert monitor._check_text_filter("Интервью дня") is True
        assert monitor._check_text_filter("Просто видео") is False
        assert monitor._check_text_filter(None) is False  # нет текста — не проходит whitelist

    def test_text_filter_stopwords(self, config, db):
        """Blacklist: блокирует посты со стоп-словами."""
        config.filter_stopwords = ["реклама", "#ad"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Отличное видео") is True
        assert monitor._check_text_filter("Реклама партнёра") is False
        assert monitor._check_text_filter("Пост с #ad тегом") is False

    def test_text_filter_both(self, config, db):
        """Whitelist + Blacklist одновременно."""
        config.filter_keywords = ["подкаст"]
        config.filter_stopwords = ["реклама"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Подкаст #42") is True
        assert monitor._check_text_filter("Подкаст — реклама") is False  # стоп-слово
        assert monitor._check_text_filter("Видео дня") is False  # нет ключевого


# ─────────────────────────────────────────────────────
# Config — новые поля
# ─────────────────────────────────────────────────────

class TestConfigNewFields:

    def test_defaults(self):
        c = Config()
        assert c.proxy is None
        assert c.session_string == ""
        assert c.buffer_channel_id == 0
        assert c.max_concurrent_downloads == 1
        assert c.max_file_size == 2 * 1024 * 1024 * 1024
        assert c.cleanup_enabled is True
        assert c.cleanup_after_hours == 48
        assert c.filter_keywords == []
        assert c.filter_stopwords == []

    def test_load_proxy(self, tmp_path):
        """Загрузка прокси из JSON."""
        import json
        from slicr.config import load_config
        creds = {"dev_mode": True, "proxy": {"type": "socks5", "host": "1.2.3.4", "port": 1080}}
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.proxy["type"] == "socks5"

    def test_load_session_string(self, tmp_path):
        """Загрузка session_string из JSON."""
        import json
        from slicr.config import load_config
        creds = {"dev_mode": True, "session_string": "abc123"}
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.session_string == "abc123"

    def test_load_filter_keywords(self, tmp_path):
        """Загрузка keywords/stopwords из JSON."""
        import json
        from slicr.config import load_config
        creds = {
            "dev_mode": True,
            "filter_keywords": ["подкаст"],
            "filter_stopwords": ["реклама"],
        }
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.filter_keywords == ["подкаст"]
        assert config.filter_stopwords == ["реклама"]
```

---

## Правила выполнения

1. **Пиши ТОЛЬКО код.** Не объясняй, не задавай вопросов.
2. **Прочитай ВСЕ указанные файлы** из секции "Обязательно прочитай" перед началом.
3. **Изучи TGF-файлы** и адаптируй паттерны, не копируй слепо.
4. **Заполняй существующие заглушки** — не создавай новых .py файлов (кроме тестов и generate_session.py).
5. **Абсолютные импорты** во всех файлах (Правило 1 из CLAUDE.md).
6. **Telethon ТОЛЬКО в `services/telegram_client.py`** — нигде больше `import telethon` (Правило 4).
7. **Pipeline-модули не импортируют друг друга** (Правило 5).
8. **Mock-режим обязателен** — код должен работать на Mac без Telegram.
9. **Не трогай** downloader.py, transcriber.py, selector.py, editor.py, publisher.py — только заглушки.
10. Тесты: `python -m pytest tests/ -v`
11. Dev-запуск: `SLICR_DEV=1 SLICR_MOCK_GPU=1 SLICR_MOCK_SELECTOR=1 python -m slicr`

## Порядок реализации

1. `config.py` — добавить новые поля + парсинг в load_config()
2. `creds.example.json` — обновить шаблон
3. `services/telegram_client.py` — полная реализация TelegramClientWrapper
4. `pipeline/monitor.py` — полная реализация TelegramMonitor
5. `__main__.py` — обновить инициализацию
6. `requirements.txt` — добавить pysocks
7. `scripts/generate_session.py` — скопировать из TGF и адаптировать
8. `tests/conftest.py` — обновить фикстуру config
9. `tests/test_stage2a.py` — написать тесты
10. Запустить тесты — все должны пройти
11. Dev-запуск — проверить mock-режим

## Критерии приёмки

### Код:
1. `services/telegram_client.py` — TelegramClientWrapper с прокси, session, forward, retry download
2. `pipeline/monitor.py` — TelegramMonitor: фильтрация видео + Source→Buffer→Tech + альбомы + текст-фильтр
3. `config.py` — новые поля (buffer_channel_id, proxy, session_string, filter_keywords/stopwords, и др.)
4. `creds.example.json` — обновлён с buffer_channel_id, proxy примерами, filter
5. `__main__.py` — инициализация TG клиента + монитора
6. `scripts/generate_session.py` — рабочий скрипт генерации сессии
7. `requirements.txt` — pysocks добавлен

### Тесты:
8. `tests/test_stage2a.py` — все тесты проходят
9. Существующие тесты (test_database.py, test_config.py, test_pipeline.py) — НЕ сломаны
10. `python -m pytest tests/ -v` — all passed

### Запуск:
11. Dev-запуск в mock-режиме — стартует без ошибок
12. В логах: "Telegram client: MOCK mode" + "TelegramMonitor running in MOCK mode" + "All modules loaded"

### Архитектура:
13. `import telethon` только в `services/telegram_client.py`
14. `pipeline/monitor.py` не импортирует telethon напрямую
15. Все импорты абсолютные
16. Mock-режим работает без Telegram
