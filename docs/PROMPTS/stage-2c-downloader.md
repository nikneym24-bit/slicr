# ЗАДАНИЕ: Этап 2c — Downloader (скачивание из Buffer после Approve)

## Роль
Ты — исполнитель. Твоя задача — реализовать скачивание видео из Buffer-канала. Stage 2a (Monitor) и Stage 2b (Bot + Модерация) уже реализованы. После нажатия Approve создаётся job(DOWNLOAD) — Downloader подхватывает и качает.

## Проект
- Путь: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /video-clipper/`
- Ветка: `stage-2/monitor-downloader` (ты на ней)
- Среда: macOS, Python 3.13, venv в `.venv/`

## Обязательно прочитай перед началом

1. `docs/CLAUDE.md` — правила проекта
2. `docs/MODULE_MAP.md` — карта модулей
3. `src/video_clipper/config.py` — конфиг (расширен в Stage 2a)
4. `src/video_clipper/constants.py` — enum-ы статусов
5. `src/video_clipper/database/models.py` — CRUD (расширен в Stage 2a-2b)
6. `src/video_clipper/services/telegram_client.py` — TelegramClientWrapper (Stage 2a)
7. Текущая заглушка: `pipeline/downloader.py`
8. `src/video_clipper/__main__.py` — точка входа (будешь обновлять)

---

## Архитектура

```
[Approve кнопка в Tech канале]
         │
         │ db.add_job(DOWNLOAD, video_id)
         ▼
┌──────────────────────────────────┐
│  Downloader Worker               │
│  (цикл каждые N сек)            │
│                                   │
│  1. db.get_next_job(DOWNLOAD)    │
│  2. db.get_video(video_id)       │
│  3. Найти сообщение в Buffer     │
│  4. tg_client.download_media()   │
│  5. db.update_video_file()       │
│  6. db.update_video_status()     │
│  7. db.update_job_status()       │
└──────────────────────────────────┘
         │
         │ status = DOWNLOADED
         ▼
   [Stage 3: Transcriber]
```

**Откуда качать:**
- Видео пересланы в Buffer-канал (Stage 2a)
- В БД хранятся source_chat_id + source_message_id (оригинал)
- Нужно также хранить buffer_message_id для скачивания из Buffer
- Скачиваем из buffer_channel_id (не из Source — Source может заблокировать)

---

## Модуль: `src/video_clipper/pipeline/downloader.py`

```python
"""
Загрузчик видео из Telegram Buffer-канала.

Подхватывает jobs типа DOWNLOAD, скачивает видео через TelegramClientWrapper,
обновляет статусы в БД.
"""

import asyncio
import logging
import os
from pathlib import Path

from video_clipper.config import Config
from video_clipper.constants import VideoStatus, JobType, JobStatus
from video_clipper.database import Database
from video_clipper.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

# Интервал проверки очереди (секунды)
POLL_INTERVAL = 5


class VideoDownloader:
    """Загрузка видео из Telegram Buffer-канала."""

    def __init__(self, config: Config, db: Database, tg_client: TelegramClientWrapper) -> None:
        self.config = config
        self.db = db
        self.tg_client = tg_client
        self._semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._running = False
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Запустить worker-цикл скачивания.

        Если config.mock_monitor == True:
          - Логировать "VideoDownloader running in MOCK mode"
          - return

        Иначе:
          - self._running = True
          - Запустить _worker() как фоновую задачу
          - Логировать "VideoDownloader started (max concurrent: {N})"
        """

    async def stop(self) -> None:
        """Остановить worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("VideoDownloader stopped")

    async def _worker(self) -> None:
        """
        Основной worker-цикл.

        while self._running:
            job = await db.get_next_job(job_type=JobType.DOWNLOAD)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            async with self._semaphore:
                await self._process_job(job)
        """

    async def _process_job(self, job: dict) -> None:
        """
        Обработать одну задачу скачивания.

        1. video = await db.get_video(job["video_id"])
        2. Если video is None → db.update_job_status(job_id, FAILED, "Video not found")
        3. await db.update_video_status(video_id, VideoStatus.DOWNLOADING)
        4. path = await self.download(job["video_id"])
        5. Если path:
             await db.update_job_status(job_id, JobStatus.COMPLETED)
        6. Если None:
             await db.update_job_status(job_id, JobStatus.FAILED, error_message)
             # Проверить attempts < max_attempts → вернуть в очередь
        """

    async def download(self, video_id: int) -> str | None:
        """
        Скачать видео по video_id.

        Алгоритм:
        1. video = await db.get_video(video_id)
        2. Если video is None → return None
        3. Определить путь сохранения:
             {config.storage_base}/downloads/{video_id}_{chat_id}_{msg_id}.mp4
        4. Создать директорию если не существует: os.makedirs(..., exist_ok=True)
        5. Получить сообщение из Buffer канала:
             messages = await tg_client.get_messages(
                 config.buffer_channel_id,
                 ids=[video["buffer_message_id"]]
             )
           Если buffer_message_id не задан — попробовать source:
             messages = await tg_client.get_messages(
                 video["source_chat_id"],
                 ids=[video["source_message_id"]]
             )
        6. result = await tg_client.download_media(
               message, file_path, progress_callback=self._make_progress_callback(video_id)
           )
        7. Если успешно:
             file_size = os.path.getsize(result)
             await db.update_video_file(video_id, result, file_size)
             await db.update_video_status(video_id, VideoStatus.DOWNLOADED)
             logger.info(f"Downloaded video {video_id}: {result} ({file_size / 1024 / 1024:.1f}MB)")
             return result
        8. Если ошибка:
             await db.update_video_status(video_id, VideoStatus.FAILED, str(e))
             logger.error(f"Failed to download video {video_id}: {e}")
             return None
        """

    def _make_progress_callback(self, video_id: int):
        """
        Создать callback для логирования прогресса.
        Логировать каждые 10%:
          "Downloading video {video_id}: {percent}% ({current_mb}/{total_mb} MB)"
        """
        last_logged = [0]  # mutable для замыкания

        def callback(current: int, total: int) -> None:
            if total == 0:
                return
            percent = int(current / total * 100)
            # Логировать каждые 10%
            if percent >= last_logged[0] + 10:
                last_logged[0] = percent
                current_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                logger.info(
                    f"Downloading video {video_id}: {percent}% ({current_mb:.1f}/{total_mb:.1f} MB)"
                )

        return callback

    async def cleanup_old_files(self) -> None:
        """
        Авто-очистка скачанных видео.

        Если config.cleanup_enabled == False → return

        1. videos = await db.get_videos_for_cleanup(config.cleanup_after_hours)
        2. Для каждого видео:
             - os.remove(video["file_path"])
             - await db.clear_video_file(video["id"])
        3. Логировать: "Cleaned up {N} old video files"
        """
```

### Mock-режим

```python
async def download(self, video_id: int) -> str | None:
    if self.config.mock_monitor:
        logger.info(f"MOCK: downloading video {video_id}")
        video = await self.db.get_video(video_id)
        if video is None:
            return None

        # Создать пустой файл
        downloads_dir = Path(self.config.storage_base) / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(
            downloads_dir / f"{video_id}_{video['source_chat_id']}_{video['source_message_id']}.mp4"
        )
        Path(file_path).touch()

        await self.db.update_video_file(video_id, file_path, 0)
        await self.db.update_video_status(video_id, VideoStatus.DOWNLOADED)
        logger.info(f"MOCK: downloaded video {video_id} → {file_path}")
        return file_path

    # ... реальное скачивание ...
```

---

## Изменения в существующих файлах

### 1. `src/video_clipper/database/models.py` — ДОБАВИТЬ

Таблица videos нуждается в buffer_message_id для хранения ID пересланного сообщения:

```python
# В init_tables() — ALTER TABLE не нужен, просто добавить колонку в CREATE TABLE:
# Но CREATE TABLE уже существует и мы не хотим менять schema...
# Решение: добавить через migrations.py ИЛИ добавить колонку buffer_message_id

# Вариант 1: Добавить миграцию
# Вариант 2: Хранить buffer_message_id в отдельном поле
# Рекомендация: добавить колонку через миграцию
```

**Миграция — добавить в `database/migrations.py`:**

```python
async def migrate_add_buffer_message_id(conn):
    """Добавить buffer_message_id в таблицу videos."""
    try:
        await conn.execute(
            "ALTER TABLE videos ADD COLUMN buffer_message_id INTEGER"
        )
    except Exception:
        pass  # Колонка уже существует
```

Вызвать миграцию в `init_tables()` после создания таблиц.

**Добавить метод в Database:**

```python
async def update_video_buffer_message(self, video_id: int, buffer_message_id: int) -> None:
    """Сохранить ID сообщения в Buffer-канале."""
    async with self._get_connection() as conn:
        await conn.execute(
            "UPDATE videos SET buffer_message_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (buffer_message_id, video_id),
        )

async def get_videos_for_cleanup(self, hours: int) -> list[dict]:
    """Видео для авто-очистки: финальный статус + файл есть + старше N часов."""
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, file_path FROM videos
            WHERE status IN ('published', 'rejected', 'failed', 'skipped')
            AND file_path IS NOT NULL
            AND updated_at < datetime('now', ? || ' hours')
            """,
            (f"-{hours}",),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def clear_video_file(self, video_id: int) -> None:
    """Очистить путь к файлу видео (после удаления файла)."""
    async with self._get_connection() as conn:
        await conn.execute(
            "UPDATE videos SET file_path = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (video_id,),
        )
```

### 2. `src/video_clipper/pipeline/monitor.py` — МОДИФИКАЦИЯ

После пересылки в Buffer, сохранить buffer_message_id:

```python
# В _process_single(), после forward в Buffer:
buffer_sent = await tg_client.forward_messages(
    to_chat_id=config.buffer_channel_id,
    from_chat_id=chat_id,
    message_ids=[message_id],
    drop_author=False,
)
buffer_message_id = buffer_sent[0].id if buffer_sent else None

# После db.add_video():
if buffer_message_id:
    await db.update_video_buffer_message(video_id, buffer_message_id)
```

### 3. `src/video_clipper/__main__.py` — ОБНОВИТЬ

Добавить инициализацию и запуск Downloader:

```python
# После инициализации Monitor:

# Downloader (Stage 2c)
from video_clipper.pipeline.downloader import VideoDownloader
downloader = VideoDownloader(config, db, tg_client)
await downloader.start()

# ... в finally:
await downloader.stop()
```

Также добавить периодическую очистку:

```python
# Cleanup task
async def periodic_cleanup():
    """Периодическая очистка старых файлов."""
    while True:
        await asyncio.sleep(3600)  # каждый час
        try:
            await downloader.cleanup_old_files()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

if config.cleanup_enabled and not config.mock_monitor:
    cleanup_task = asyncio.create_task(periodic_cleanup())
```

---

## Тесты

### Файл: `tests/test_stage2c.py`

```python
"""Тесты для Stage 2c: VideoDownloader."""

import pytest
import pytest_asyncio
from pathlib import Path

from video_clipper.config import Config
from video_clipper.database import Database
from video_clipper.constants import VideoStatus, JobType, JobStatus


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
        tech_channel_id=0,
        target_channel_id=0,
        buffer_channel_id=-1008888888888,
        claude_api_key="test",
        vk_access_token="test",
        vk_group_id=0,
        source_channels=[],
        storage_base=str(tmp_path / "storage"),
        max_concurrent_downloads=1,
        max_file_size=2 * 1024 * 1024 * 1024,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        proxy=None,
        session_string="",
        filter_keywords=[],
        filter_stopwords=[],
    )


class TestVideoDownloader:

    def test_init(self, config, db):
        """Инициализация загрузчика."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        assert dl._running is False

    async def test_download_nonexistent(self, config, db):
        """Скачивание несуществующего видео → None."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        result = await dl.download(9999)
        assert result is None

    async def test_mock_download(self, config, db):
        """Mock-режим: создаёт пустой файл."""
        config.mock_monitor = True
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)

        video_id = await db.add_video(
            source_chat_id=-1001234567890,
            source_message_id=100,
            duration=60.0,
            file_size=1024 * 1024,
        )

        result = await dl.download(video_id)
        assert result is not None
        assert Path(result).exists()
        assert result.endswith(".mp4")

        video = await db.get_video(video_id)
        assert video["status"] == VideoStatus.DOWNLOADED
        assert video["file_path"] == result

    async def test_mock_download_creates_directory(self, config, db):
        """Mock: создаёт директорию downloads/ если не существует."""
        config.mock_monitor = True
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)

        video_id = await db.add_video(-100, 1, duration=60)
        result = await dl.download(video_id)

        downloads_dir = Path(config.storage_base) / "downloads"
        assert downloads_dir.exists()

    async def test_cleanup_no_files(self, config, db):
        """Очистка при пустой БД."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        await dl.cleanup_old_files()  # не должен упасть

    async def test_cleanup_disabled(self, config, db):
        """Очистка отключена в конфиге."""
        config.cleanup_enabled = False
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        await dl.cleanup_old_files()  # не должен упасть

    def test_progress_callback(self, config, db):
        """Прогресс-callback не падает."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        cb = dl._make_progress_callback(1)
        cb(0, 100)
        cb(50, 100)
        cb(100, 100)
        cb(0, 0)  # edge case


class TestDatabaseCleanupMethods:

    async def test_get_videos_for_cleanup_empty(self, db):
        """Пустая БД — нет видео для очистки."""
        videos = await db.get_videos_for_cleanup(48)
        assert videos == []

    async def test_clear_video_file(self, db):
        """Очистка пути к файлу."""
        video_id = await db.add_video(-100, 1, duration=60)
        await db.update_video_file(video_id, "/tmp/test.mp4", 1024)

        video = await db.get_video(video_id)
        assert video["file_path"] == "/tmp/test.mp4"

        await db.clear_video_file(video_id)
        video = await db.get_video(video_id)
        assert video["file_path"] is None

    async def test_update_video_buffer_message(self, db):
        """Сохранение buffer_message_id."""
        video_id = await db.add_video(-100, 1, duration=60)
        await db.update_video_buffer_message(video_id, 12345)
        video = await db.get_video(video_id)
        assert video["buffer_message_id"] == 12345
```

---

## Правила выполнения

1. **Пиши ТОЛЬКО код.**
2. **Прочитай ВСЕ указанные файлы** перед началом.
3. **Заполняй существующую заглушку** `pipeline/downloader.py`.
4. **Абсолютные импорты** (Правило 1).
5. **Telethon только через TelegramClientWrapper** (Правило 4).
6. **Downloader не импортирует monitor.py** (Правило 5).
7. **Mock-режим обязателен.**
8. Тесты: `python -m pytest tests/ -v`

## Порядок реализации

1. `database/migrations.py` — миграция buffer_message_id
2. `database/models.py` — новые методы (update_video_buffer_message, get_videos_for_cleanup, clear_video_file)
3. `pipeline/monitor.py` — сохранять buffer_message_id после пересылки
4. `pipeline/downloader.py` — полная реализация VideoDownloader
5. `__main__.py` — добавить Downloader + cleanup task
6. `tests/test_stage2c.py` — тесты
7. Запустить все тесты

## Критерии приёмки

### Код:
1. `pipeline/downloader.py` — VideoDownloader с worker-циклом, семафором, progress, mock, cleanup
2. `database/models.py` — update_video_buffer_message, get_videos_for_cleanup, clear_video_file
3. `database/migrations.py` — миграция buffer_message_id
4. `pipeline/monitor.py` — сохранение buffer_message_id
5. `__main__.py` — Downloader запускается + periodic cleanup

### Тесты:
6. `tests/test_stage2c.py` — все тесты проходят
7. Существующие тесты — НЕ сломаны
8. `python -m pytest tests/ -v` — all passed

### Запуск:
9. Mock-режим стартует без ошибок

### Архитектура:
10. `import telethon` только в `services/telegram_client.py`
11. `downloader.py` не импортирует `monitor.py`
12. Все импорты абсолютные
