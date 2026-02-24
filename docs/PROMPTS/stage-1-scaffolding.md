# ЗАДАНИЕ: Этап 1 — Scaffolding + DB + Config + Dev Launcher

## Роль
Ты — исполнитель. Архитектор уже принял все решения. Твоя задача — реализовать код ТОЧНО по спецификации. Не меняй архитектуру, не добавляй своё, не пропускай ничего.

## Проект
- Путь: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr/`
- Ветка: `stage-1/scaffolding` (уже создана, ты на ней)
- GitHub: https://github.com/nikneym24-bit/slicr
- Сейчас в репо: .gitignore, README.md, docs/ (CLAUDE.md, MODULE_MAP.md, CONTRIBUTING.md, DEVELOPMENT_STANDARDS.md), .claude/, .claudeignore
- Среда: macOS (MacBook), Python 3.13, без NVIDIA GPU

## Обязательно прочитай перед началом
1. `docs/CLAUDE.md` — инструкции проекта
2. `docs/MODULE_MAP.md` — карта модулей
3. Файл архитектуры: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /ARCHITECTURE.md`

## Что создать

### Структура файлов (создай ВСЕ):

```
slicr/
├── main.py                         # Точка входа — РЕАЛИЗОВАТЬ
├── config.py                       # Конфигурация — РЕАЛИЗОВАТЬ
├── constants.py                    # Enum-ы — РЕАЛИЗОВАТЬ
├── requirements.txt                # Зависимости — РЕАЛИЗОВАТЬ
├── dev.command                     # macOS лаунчер — РЕАЛИЗОВАТЬ
├── creds.example.json              # Шаблон конфига — РЕАЛИЗОВАТЬ
│
├── pipeline/
│   ├── __init__.py
│   ├── orchestrator.py             # ЗАГЛУШКА
│   ├── monitor.py                  # ЗАГЛУШКА
│   ├── downloader.py               # ЗАГЛУШКА
│   ├── transcriber.py              # ЗАГЛУШКА
│   ├── selector.py                 # ЗАГЛУШКА
│   ├── editor.py                   # ЗАГЛУШКА
│   └── publisher.py                # ЗАГЛУШКА
│
├── gpu/
│   ├── __init__.py
│   ├── guard.py                    # ЗАГЛУШКА
│   └── monitor.py                  # ЗАГЛУШКА
│
├── database/
│   ├── __init__.py                 # Реэкспорт Database
│   ├── connection.py               # РЕАЛИЗОВАТЬ ПОЛНОСТЬЮ
│   ├── models.py                   # РЕАЛИЗОВАТЬ ПОЛНОСТЬЮ
│   └── migrations.py               # РЕАЛИЗОВАТЬ ПОЛНОСТЬЮ
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py                 # ЗАГЛУШКА
│   ├── moderation.py               # ЗАГЛУШКА
│   └── keyboards.py                # ЗАГЛУШКА
│
├── services/
│   ├── __init__.py
│   ├── claude_client.py            # ЗАГЛУШКА
│   ├── vk_clips.py                 # ЗАГЛУШКА
│   └── telegram_client.py          # ЗАГЛУШКА
│
├── utils/
│   ├── __init__.py
│   ├── video.py                    # ЗАГЛУШКА
│   ├── subtitles.py                # ЗАГЛУШКА
│   └── logging_config.py           # РЕАЛИЗОВАТЬ ПОЛНОСТЬЮ
│
├── storage/
│   ├── downloads/.gitkeep
│   ├── clips/.gitkeep
│   └── temp/.gitkeep
│
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Фикстуры — РЕАЛИЗОВАТЬ
    ├── test_database.py            # РЕАЛИЗОВАТЬ
    └── test_config.py              # РЕАЛИЗОВАТЬ
```

---

## Спецификации модулей

### 1. constants.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

```python
from enum import StrEnum

class VideoStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    SELECTING = "selecting"
    SELECTED = "selected"
    PROCESSING = "processing"
    READY = "ready"
    MODERATION = "moderation"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    FAILED = "failed"
    SKIPPED = "skipped"

class JobType(StrEnum):
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    SELECT = "select"
    EDIT = "edit"
    PUBLISH = "publish"

class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Platform(StrEnum):
    VK_CLIPS = "vk_clips"
    TELEGRAM = "telegram"
```

---

### 2. config.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

Загружает из `creds.json` + переменные окружения. Паттерн из TGForwardez.

Класс Config с полями:
- Telegram: api_id (int), api_hash (str), bot_token (str), admin_id (int), tech_channel_id (int), target_channel_id (int)
- Claude API: claude_api_key (str), claude_model (str, default "claude-sonnet-4-20250514")
- VK: vk_access_token (str), vk_group_id (int)
- Pipeline: min_video_duration=30, max_video_duration=7200, min_clip_duration=15, max_clip_duration=60
- Whisper: whisper_model="medium", whisper_compute_type="int8", whisper_language="ru"
- GPU Guard: gpu_guard_enabled=True, gpu_min_free_vram_gb=3.0
- Storage: storage_base="./storage"
- Source channels: source_channels (list[int])
- Dev mode: dev_mode (bool), mock_gpu (bool), mock_selector (bool), mock_monitor (bool)
- DB: db_path (str, default "slicr.db")

Функция `load_config(path="creds.json") -> Config`:
- Читает JSON файл
- Переменные окружения перезаписывают JSON: SLICR_DEV=1 → dev_mode=True, SLICR_MOCK_GPU=1 → mock_gpu=True, SLICR_MOCK_SELECTOR=1 → mock_selector=True, SLICR_MOCK_MONITOR=1 → mock_monitor=True
- Если файл не найден и dev_mode=True → работает с дефолтами
- Если файл не найден и dev_mode=False → raise ConfigError с понятным сообщением

---

### 3. database/connection.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

Паттерн ConnectionMixin из TGForwardez:

```python
class ConnectionMixin:
    db_path: str
    _conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        # Кэширует одно долгоживущее соединение
        # PRAGMA: foreign_keys=ON, journal_mode=WAL, busy_timeout=5000
        # row_factory = aiosqlite.Row
        # commit при успехе, rollback при ошибке

    async def close(self) -> None:
        # Закрыть соединение
```

### 4. database/models.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

Класс `Database(ConnectionMixin)` с методами:

**init_tables()** — создание 7 таблиц (SQL из ARCHITECTURE.md секция 4):
- videos (с UNIQUE(source_chat_id, source_message_id))
- transcriptions
- clips
- jobs
- publications
- sources
- settings

**Методы CRUD:**
- `add_video(source_chat_id, source_message_id, duration=None, caption=None, file_size=None, width=None, height=None) -> int` — возвращает video_id
- `get_video(video_id) -> dict | None`
- `update_video_status(video_id, status, error_message=None)`
- `update_video_file(video_id, file_path, file_size=None)`
- `is_duplicate(source_chat_id, source_message_id) -> bool`
- `add_transcription(video_id, full_text, segments_json=None, words_json=None, language=None, model_name=None, processing_time=None) -> int`
- `add_clip(video_id, transcription_id, start_time, end_time, duration, title=None, description=None, ai_reason=None, ai_score=None, transcript_fragment=None) -> int`
- `update_clip_status(clip_id, status)`
- `update_clip_paths(clip_id, raw_clip_path=None, final_clip_path=None, subtitle_path=None)`
- `add_job(video_id=None, clip_id=None, job_type, requires_gpu=False, priority=0) -> int`
- `get_next_job(job_type=None, requires_gpu=None) -> dict | None` — берёт самый старый со статусом queued, ставит running
- `update_job_status(job_id, status, error_message=None)`
- `add_source(chat_id, chat_title=None, chat_username=None)`
- `get_active_sources() -> list[dict]`
- `add_publication(clip_id, platform, platform_post_id=None) -> int`
- `get_setting(key, default=None) -> str | None`
- `set_setting(key, value)`

### 5. database/migrations.py — РЕАЛИЗОВАТЬ

- Хранит версию в settings (key='schema_version')
- При запуске проверяет текущую версию
- Версия 1 = начальная схема (init_tables)
- Метод `run_migrations()` вызывается после init_tables

### 6. database/__init__.py

```python
from database.models import Database

__all__ = ["Database"]
```

---

### 7. utils/logging_config.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

```python
def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    # Консоль: StreamHandler, формат: [HH:MM:SS] LEVEL module — message
    # Файл: logs/slicr.log, RotatingFileHandler (10 MB, 5 backups)
    # Формат файла: [YYYY-MM-DD HH:MM:SS] [LEVEL] [module] message
    # Создаёт log_dir если не существует
```

---

### 8. main.py — ПОЛНАЯ РЕАЛИЗАЦИЯ

```python
import asyncio
import logging
from config import load_config
from database import Database
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════╗
║        VIDEO CLIPPER v0.1.0          ║
║   Telegram → Clips → VK / Telegram  ║
╚══════════════════════════════════════╝
"""

async def main():
    # 1. Загрузить конфиг
    config = load_config()

    # 2. Настроить логирование
    setup_logging()

    # 3. Показать баннер
    print(BANNER)
    logger.info("Starting Video Clipper...")

    # 4. Показать режим
    if config.dev_mode:
        logger.info("MODE: Development")
        logger.info(f"  Mock GPU:      {config.mock_gpu}")
        logger.info(f"  Mock Selector: {config.mock_selector}")
        logger.info(f"  Mock Monitor:  {config.mock_monitor}")
    else:
        logger.info("MODE: Production")

    # 5. Инициализировать БД
    db = Database(config.db_path)
    await db.init_tables()
    logger.info(f"Database ready: {config.db_path}")

    # 6. Импортировать заглушки — проверка что всё грузится
    from pipeline.orchestrator import PipelineOrchestrator
    from pipeline.monitor import TelegramMonitor
    from pipeline.transcriber import WhisperTranscriber
    from pipeline.selector import MomentSelector
    from pipeline.editor import VideoEditor
    from pipeline.publisher import ClipPublisher
    from gpu.guard import GPUGuard

    logger.info("All modules loaded (stubs)")
    logger.info("Pipeline ready. Stages not yet implemented.")
    logger.info("Waiting for stage-2 implementation...")

    # 7. Держим процесс
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await db.close()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 9. dev.command — macOS лаунчер

```bash
#!/bin/bash
# dev.command — Video Clipper Dev Launcher
# Двойной клик в Finder для запуска

cd "$(dirname "$0")"

echo "==============================="
echo "  Video Clipper — Dev Mode"
echo "==============================="
echo ""

# Python check
if ! command -v python3 &> /dev/null; then
    echo "ОШИБКА: Python3 не найден!"
    echo "Установите: brew install python@3.13"
    read -p "Нажмите Enter..."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $PYTHON_VERSION"

# venv
if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# deps
if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ]; then
    echo "Устанавливаю зависимости..."
    pip install -q -r requirements.txt
    touch .venv/.deps_installed
fi

# dirs
mkdir -p storage/downloads storage/clips storage/temp logs

# creds check
if [ ! -f "creds.json" ]; then
    echo ""
    echo "Файл creds.json не найден."
    echo "Копирую creds.example.json -> creds.json"
    echo "Заполните свои данные позже."
    echo ""
    cp creds.example.json creds.json 2>/dev/null
fi

# Dev env vars
export SLICR_DEV=1
export SLICR_MOCK_GPU=1
export SLICR_MOCK_SELECTOR=1

echo ""
echo "Режим: DEV (mock GPU, mock Selector)"
echo "==============================="
echo ""

python3 main.py

echo ""
read -p "Нажмите Enter для выхода..."
```

После создания файла — выполни `chmod +x dev.command`.

---

### 10. creds.example.json

```json
{
    "api_id": 0,
    "api_hash": "YOUR_API_HASH",
    "bot_token": "YOUR_BOT_TOKEN",
    "admin_id": 0,
    "tech_channel_id": 0,
    "target_channel_id": 0,

    "claude_api_key": "sk-ant-YOUR_KEY",
    "claude_model": "claude-sonnet-4-20250514",

    "vk_access_token": "YOUR_VK_TOKEN",
    "vk_group_id": 0,

    "source_channels": [],

    "dev_mode": true,
    "mock_gpu": true,
    "mock_selector": true,
    "mock_monitor": true
}
```

---

### 11. requirements.txt

```
# Telegram
aiogram>=3.20.0
telethon>=1.40.0

# AI
anthropic>=0.40.0

# Video / Audio
faster-whisper>=1.1.0
ffmpeg-python>=0.2.0

# Database
aiosqlite>=0.21.0

# GPU (optional — not available on Mac)
# pynvml>=12.0.0

# Utils
python-dotenv>=1.0.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

---

### 12. Заглушки (pipeline/, gpu/, bot/, services/, utils/)

Каждая заглушка — файл с:
1. Docstring: что модуль делает (на русском), в каком этапе реализация
2. Класс с `__init__(self, config, db)` + `logger`
3. Основные методы как async заглушки с `logger.warning("... not implemented yet")`

Имена классов и методы:
- `pipeline/orchestrator.py` → `PipelineOrchestrator` (start, stop, process_video)
- `pipeline/monitor.py` → `TelegramMonitor` (start, stop)
- `pipeline/downloader.py` → `VideoDownloader` (download)
- `pipeline/transcriber.py` → `WhisperTranscriber` (transcribe)
- `pipeline/selector.py` → `MomentSelector` (select_moment)
- `pipeline/editor.py` → `VideoEditor` (create_clip)
- `pipeline/publisher.py` → `ClipPublisher` (publish_vk, publish_telegram)
- `gpu/guard.py` → `GPUGuard` (check_available, acquire, release)
- `gpu/monitor.py` → `GPUWatchdog` (start_watching, stop_watching)
- `bot/handlers.py` → `setup_handlers(dp, config, db)` функция
- `bot/moderation.py` → `setup_moderation(dp, config, db)` функция
- `bot/keyboards.py` → `get_moderation_keyboard(clip_id)` функция
- `services/claude_client.py` → `ClaudeClient` (analyze_transcript)
- `services/vk_clips.py` → `VKClipsClient` (upload_clip)
- `services/telegram_client.py` → `TelegramClientWrapper` (connect, disconnect)
- `utils/video.py` → функции: `crop_to_vertical()`, `extract_segment()`
- `utils/subtitles.py` → функции: `generate_srt()`, `generate_ass()`

---

### 13. Тесты

#### tests/conftest.py
- Фикстура `db` — создаёт in-memory БД (путь `:memory:` или tmpdir), вызывает init_tables(), yield, close
- Фикстура `config` — возвращает Config с dev_mode=True и всеми mock=True

#### tests/test_database.py
Тесты (все async, используй pytest-asyncio):
- `test_init_tables` — БД создаётся, все 7 таблиц существуют (проверить через sqlite_master)
- `test_add_video` — добавить видео, получить по id, проверить поля
- `test_duplicate_video` — добавить дубль → is_duplicate возвращает True
- `test_video_status_update` — обновить статус, проверить
- `test_add_job_and_get_next` — создать задачу, get_next_job возвращает её, статус стал running
- `test_get_next_job_empty` — пустая очередь → None
- `test_settings` — set_setting / get_setting
- `test_sources` — add_source / get_active_sources

#### tests/test_config.py
- `test_load_config_from_file` — создать tmp creds.json, загрузить, проверить поля
- `test_dev_mode_from_env` — установить env SLICR_DEV=1, проверить config.dev_mode == True
- `test_missing_creds_raises` — без файла и без dev_mode → ConfigError

---

## Правила выполнения

1. **Пиши ТОЛЬКО код.** Не объясняй, не задавай вопросов.
2. Python 3.13, type hints, StrEnum. Async/await везде где IO.
3. Логирование через `logging` (не print, кроме баннера в main.py).
4. Код на английском. Docstrings и комментарии на русском допустимы.
5. Не создавай creds.json (только creds.example.json).
6. storage/ — с .gitkeep файлами.
7. После создания ВСЕХ файлов:
   - `chmod +x dev.command`
   - Запусти тесты: `cd "/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr" && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m pytest tests/ -v`
   - Если тесты падают — ИСПРАВЬ.
   - Запусти `python3 main.py` с SLICR_DEV=1 — убедись что стартует без ошибок, покажи вывод.

## Критерии приёмки

1. `./dev.command` запускается на Mac — создаёт venv, ставит deps, показывает баннер
2. БД создаётся, все 7 таблиц на месте
3. Все тесты проходят (pytest green)
4. Все заглушки имеют осмысленные docstrings и классы с правильными сигнатурами
5. `main.py` стартует в dev-режиме без ошибок и показывает статус mock-ов
