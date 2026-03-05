# Параллельная сборка прототипа Slicr

> **Дата:** 2026-03-03
> **Цель:** Рабочий прототип за 1 день с 4 параллельными Claude Code сессиями
> **Уровень:** Прототип с сырыми функциями для показа руководству

---

## Общая схема

```
┌─────────────────────────────────────────────────────────────────┐
│  СЕССИЯ 0: REVIEWER (Opus) — контроль + интеграция              │
│  Запускается ПОСЛЕДНЕЙ, после завершения сессий 1-3             │
│  Мержит ветки, пишет orchestrator + __main__.py, прогоняет тесты│
└──────────────────────────┬──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ СЕССИЯ 1        │ │ СЕССИЯ 2     │ │ СЕССИЯ 3         │
│ GPU + Transcribe│ │ AI + Publish │ │ Video Editor     │
│                 │ │              │ │                  │
│ transcriber.py  │ │ claude_cl.py │ │ editor.py        │
│ gpu/guard.py    │ │ selector.py  │ │ utils/video.py   │
│ gpu/monitor.py  │ │ publisher.py │ │ utils/subtitles.py│
│                 │ │              │ │                  │
│ Ветка:          │ │ Ветка:       │ │ Ветка:           │
│ feat/gpu-transcr│ │ feat/ai-pub  │ │ feat/editor      │
└─────────────────┘ └──────────────┘ └──────────────────┘
```

---

## ПЕРЕД СТАРТОМ: Git-подготовка

Выполнить в терминале ОДИН раз перед запуском сессий:

```bash
cd "/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr"
git init
git add -A
git commit -m "chore: baseline before parallel build"
git branch feat/gpu-transcribe
git branch feat/ai-publish
git branch feat/editor
```

Каждая сессия работает в своей ветке. Сессия 0 мержит в main.

---

## ОБЩИЕ ПРАВИЛА ДЛЯ ВСЕХ СЕССИЙ

### Обязательно прочитать перед работой:
- `docs/CLAUDE.md` — архитектурные правила
- `docs/MODULE_MAP.md` — карта модулей
- `src/slicr/constants.py` — enum-ы (VideoStatus, JobType, JobStatus)
- `src/slicr/config.py` — класс Config (все настройки)
- `src/slicr/database/models.py` — Database API (какие методы уже есть)

### Паттерны проекта:
```python
# Логирование
import logging
logger = logging.getLogger(__name__)

# Абсолютные импорты
from slicr.config import Config
from slicr.constants import VideoStatus, JobType, JobStatus
from slicr.database import Database

# Async DB
async with self._get_connection() as conn:
    await conn.execute("SELECT ...", (param,))

# Type hints обязательны
async def method(self, video_id: int) -> str | None:

# Enum-ы вместо строк
await self.db.update_video_status(video_id, VideoStatus.TRANSCRIBED)
```

### НЕ ТРОГАТЬ (зарезервировано для Сессии 0):
- `src/slicr/__main__.py`
- `src/slicr/pipeline/orchestrator.py`
- `src/slicr/pipeline/__init__.py`
- `src/slicr/services/__init__.py`
- `src/slicr/gpu/__init__.py`
- `src/slicr/utils/__init__.py`

### Mock-режим:
Каждый модуль ОБЯЗАН поддерживать mock через `config`:
```python
if self.config.mock_gpu:
    logger.info("Mock режим: пропускаем GPU проверку")
    return True
```

### После написания кода:
```bash
ruff check src/slicr/path/to/file.py
python -m pytest tests/ -x -q --timeout=120
```

---

## ЗАМОРОЖЕННЫЕ ИНТЕРФЕЙСЫ

> Эти сигнатуры НЕ МЕНЯТЬ. Реализация внутри — свободная.

### Database API (уже реализовано, использовать as-is):

```python
# Видео
await db.add_video(source_chat_id, source_message_id, file_path, file_size, duration, width, height, caption, priority) -> int
await db.get_video(video_id) -> dict | None
await db.update_video_status(video_id, status: VideoStatus, error_message=None) -> None
await db.update_video_file(video_id, file_path, file_size, duration, width, height) -> None

# Транскрипции
await db.add_transcription(video_id, full_text, language, segments_json, words_json, model_name, processing_time) -> int
await db.get_transcription(transcription_id) -> dict | None
await db.get_transcription_by_video(video_id) -> dict | None

# Клипы
await db.add_clip(video_id, transcription_id, start_time, end_time, duration, title, description, ai_reason, ai_score, transcript_fragment, raw_clip_path) -> int
await db.get_clip(clip_id) -> dict | None
await db.update_clip_paths(clip_id, final_clip_path, subtitle_path) -> None
await db.update_clip_status(clip_id, status: VideoStatus) -> None
await db.update_clip_moderation_message(clip_id, message_id) -> None

# Публикации
await db.add_publication(clip_id, platform: Platform, platform_post_id) -> int

# Задачи
await db.add_job(video_id, job_type: JobType, priority=0, requires_gpu=False, clip_id=None) -> int
await db.get_next_job(job_type: JobType, requires_gpu=None) -> dict | None
await db.update_job_status(job_id, status: JobStatus, error_message=None) -> None
await db.increment_job_attempts(job_id) -> int

# Источники
await db.get_active_sources() -> list[dict]

# Настройки
await db.get_setting(key) -> str | None
await db.set_setting(key, value) -> None
```

### Config (ключевые поля, уже реализовано):

```python
@dataclass
class Config:
    # Telegram
    api_id: int
    api_hash: str
    bot_token: str
    admin_id: int
    tech_channel_id: int
    target_channel_id: int

    # AI
    claude_api_key: str

    # VK
    vk_access_token: str

    # Whisper
    whisper_model: str = "medium"          # small/medium/large-v3
    whisper_compute_type: str = "int8"
    whisper_language: str = "ru"
    whisper_device: str = "cuda"

    # GPU Guard
    gpu_min_free_vram_gb: float = 3.0
    gpu_max_utilization: int = 30
    gpu_check_interval: float = 2.0

    # Clip settings
    min_clip_duration: float = 15.0
    max_clip_duration: float = 60.0
    target_width: int = 1080
    target_height: int = 1920

    # Storage
    storage_dir: str = "storage"
    downloads_dir: str = "storage/downloads"
    clips_dir: str = "storage/clips"
    temp_dir: str = "storage/temp"

    # Dev/Mock
    dev_mode: bool = False
    mock_gpu: bool = False
    mock_selector: bool = False
    mock_monitor: bool = False

    # Source channels
    source_channels: list[int] = field(default_factory=list)
```

---

## СЕССИЯ 1: GPU + Transcriber

### Промпт для запуска сессии:

```
Ты работаешь над проектом Slicr — автоматический видео-нарезчик.
Прочитай docs/PARALLEL_BUILD_PLAN.md — там твоё задание (СЕССИЯ 1).
Прочитай docs/CLAUDE.md и docs/MODULE_MAP.md для контекста.
Переключись на ветку feat/gpu-transcribe и начинай работу.
```

### Ветка: `feat/gpu-transcribe`

### Файлы для реализации:

#### 1. `src/slicr/gpu/guard.py` — GPUGuard

```python
class GPUGuard:
    def __init__(self, config: Config, db: Database) -> None
    async def check_available(self) -> bool
    async def acquire(self) -> bool
    async def release(self) -> None
```

**Требования:**
- Использовать `pynvml` для чтения VRAM, utilization, процессов
- `check_available()`: свободно >= `config.gpu_min_free_vram_gb` GB И utilization < `config.gpu_max_utilization`%
- `acquire()`: вызывает `check_available()`, если True — помечает GPU как занятый (внутренний флаг `_acquired`)
- `release()`: сбрасывает `_acquired`
- **Mock-режим:** если `config.mock_gpu` — всегда возвращать True / пропускать
- `pynvml.nvmlInit()` в конструкторе, `nvmlShutdown()` в деструкторе
- Логировать: свободную VRAM, utilization, решение (ALLOW/DENY)

#### 2. `src/slicr/gpu/monitor.py` — GPUWatchdog

```python
class GPUWatchdog:
    def __init__(self, config: Config, db: Database) -> None
    async def start_watching(self) -> None
    async def stop_watching(self) -> None
```

**Требования:**
- Фоновый `asyncio.Task`, опрос каждые `config.gpu_check_interval` секунд
- Если свободная VRAM < 1 GB → установить `self.should_abort = True`
- Логировать текущую VRAM при каждом опросе (DEBUG) и при ABORT (WARNING)
- Mock: ничего не делать

#### 3. `src/slicr/pipeline/transcriber.py` — WhisperTranscriber

```python
class WhisperTranscriber:
    def __init__(self, config: Config, db: Database) -> None
    async def transcribe(self, video_id: int) -> int | None
```

**Требования:**
- Использовать `faster_whisper.WhisperModel`
- Модель загружать ЛЕНИВО (при первом вызове `transcribe`), хранить в `self._model`
- Перед загрузкой модели — `GPUGuard.acquire()`, после транскрибации — `GPUGuard.release()`
- Параметры из config: `whisper_model`, `whisper_compute_type`, `whisper_language`, `whisper_device`
- `transcribe()`:
  1. `db.get_video(video_id)` → получить `file_path`
  2. `db.update_video_status(video_id, VideoStatus.TRANSCRIBING)`
  3. Запустить whisper в `asyncio.to_thread()` (блокирующий вызов)
  4. Собрать segments и words с таймкодами
  5. `db.add_transcription(...)` → вернуть `transcription_id`
  6. `db.update_video_status(video_id, VideoStatus.TRANSCRIBED)`
  7. При ошибке: `VideoStatus.FAILED`, вернуть None
- **ПОСЛЕ транскрибации — ВЫГРУЗИТЬ модель** (`del self._model; self._model = None`) + `torch.cuda.empty_cache()` если доступен
- Mock: если `config.mock_gpu` — вернуть фейковую транскрипцию с 3-5 словами и таймкодами
- Формат words_json: `[{"word": "привет", "start": 0.0, "end": 0.5}, ...]`
- Формат segments_json: `[{"start": 0.0, "end": 5.0, "text": "привет мир"}, ...]`

### Тесты:
Создать `tests/test_transcriber.py`:
- Тест mock-режима (transcribe возвращает transcription_id)
- Тест что статус видео обновляется корректно
- Тест что при ошибке статус = FAILED

### НЕ ТРОГАТЬ:
- `__main__.py`, `orchestrator.py`, любые `__init__.py`
- Файлы pipeline кроме `transcriber.py`
- Файлы services/, utils/, bot/

---

## СЕССИЯ 2: AI Selection + Publisher

### Статус: ЧАСТИЧНО ВЫПОЛНЕНА (2026-03-05)

**Выполнено:**
- ✅ `claude_client.py` — полная реализация (aiohttp + CF Worker прокси, rate limiter 50 RPM, retry с exponential backoff, health_check)
- ✅ `selector.py` — полная реализация (получает транскрипцию из БД, отправляет в Claude, сохраняет clip)
- ✅ Cloudflare Worker — универсальный AI API прокси (claude/gemini/groq)
- ✅ `config.py` — добавлено поле `claude_proxy_url`
- ✅ Live-тест через прокси пройден (health check + analyze_transcript)

**Осталось:**
- ❌ `publisher.py` — публикация в Telegram/VK (заглушка)

### Ветка: `main` (реализовано напрямую)

### Реализованные файлы:

#### 1. `src/slicr/services/claude_client.py` — ClaudeClient ✅

```python
class ClaudeClient:
    def __init__(self, config: Config) -> None
    async def analyze_transcript(self, transcript: str, duration: float) -> dict | None
    async def health_check(self) -> bool
    async def close(self) -> None
```

**Реализация:**
- HTTP-клиент через `aiohttp` (не `anthropic` SDK) для совместимости с CF Worker прокси
- `claude_proxy_url` → Cloudflare Worker → `api.anthropic.com` (обход гео-блокировок)
- Rate limiter: 50 req/min с async lock
- Retry: exponential backoff для 429/500/502/503/504
- JSON-парсинг с очисткой markdown-обёрток
- Валидация таймкодов и автокоррекция длительности клипа

#### 2. `src/slicr/pipeline/selector.py` — MomentSelector

```python
class MomentSelector:
    def __init__(self, config: Config, db: Database) -> None
    async def select_moment(self, video_id: int, transcription_id: int) -> int | None
```

**Требования:**
- `select_moment()`:
  1. `db.update_video_status(video_id, VideoStatus.SELECTING)`
  2. `db.get_transcription(transcription_id)` → получить `full_text`, `words_json`
  3. `db.get_video(video_id)` → получить `duration`
  4. Вызвать `ClaudeClient.analyze_transcript(full_text, duration)`
  5. Если результат None → `VideoStatus.SKIPPED`, вернуть None
  6. `db.add_clip(...)` с данными из Claude → получить `clip_id`
  7. `db.update_video_status(video_id, VideoStatus.SELECTED)`
  8. Вернуть `clip_id`
- Создать `ClaudeClient` в конструкторе
- При ошибке: `VideoStatus.FAILED`, вернуть None

#### 3. `src/slicr/pipeline/publisher.py` — ClipPublisher

```python
class ClipPublisher:
    def __init__(self, config: Config, db: Database) -> None
    async def publish_telegram(self, clip_id: int) -> str | None
    async def publish_vk(self, clip_id: int) -> str | None
```

**Требования для `publish_telegram()`:**
- Получить клип: `db.get_clip(clip_id)` → `final_clip_path`, `title`, `description`
- Отправить видео через aiogram Bot:
  ```python
  from aiogram import Bot
  bot = Bot(token=self.config.bot_token)
  result = await bot.send_video(
      chat_id=self.config.target_channel_id,
      video=FSInputFile(final_clip_path),
      caption=f"{title}\n\n{description}",
  )
  ```
- Сохранить: `db.add_publication(clip_id, Platform.TELEGRAM, str(result.message_id))`
- Вернуть `str(result.message_id)`

**Требования для `publish_vk()` (ЗАГЛУШКА для прототипа):**
- Просто логировать `logger.warning("VK Clips публикация: пока не реализовано")`
- Вернуть None
- TODO-комментарий с описанием будущей реализации (upload server → upload → save)

### Тесты:
Создать `tests/test_selector.py`:
- Тест mock-режима ClaudeClient
- Тест что select_moment создаёт clip в БД
- Тест валидации (start_time < end_time)

Создать `tests/test_publisher.py`:
- Тест publish_vk возвращает None (заглушка)

### НЕ ТРОГАТЬ:
- `__main__.py`, `orchestrator.py`, любые `__init__.py`
- Файлы gpu/, utils/, bot/
- Файлы pipeline кроме `selector.py` и `publisher.py`

---

## СЕССИЯ 3: Video Editor

### Промпт для запуска сессии:

```
Ты работаешь над проектом Slicr — автоматический видео-нарезчик.
Прочитай docs/PARALLEL_BUILD_PLAN.md — там твоё задание (СЕССИЯ 3).
Прочитай docs/CLAUDE.md и docs/MODULE_MAP.md для контекста.
Переключись на ветку feat/editor и начинай работу.
```

### Ветка: `feat/editor`

### Файлы для реализации:

#### 1. `src/slicr/utils/video.py` — ffmpeg утилиты

```python
async def extract_segment(input_path: str, output_path: str, start_time: float, end_time: float) -> str | None
async def crop_to_vertical(input_path: str, output_path: str, width: int = 1080, height: int = 1920) -> str | None
```

**Требования для `extract_segment()`:**
- Вырезать фрагмент видео по таймкодам
- ffmpeg: `-ss start_time -to end_time -c copy` (быстро, без перекодировки)
- Если `-c copy` даёт артефакты на стыках, использовать `-c:v libx264 -c:a aac`
- Запускать через `asyncio.create_subprocess_exec`
- Вернуть `output_path` при успехе, None при ошибке
- Логировать команду ffmpeg (DEBUG) и результат (INFO)

**Требования для `crop_to_vertical()`:**
- Кроп из горизонтального (16:9) в вертикальный (9:16)
- Стратегия для прототипа: **center-crop** (вырезать центральную полосу)
- ffmpeg filter: `crop=ih*9/16:ih` (ширина = высота * 9/16, берём центр)
- Затем scale до `width x height`: `scale=1080:1920`
- Кодек: `-c:v libx264 -preset medium -crf 23 -c:a aac`
- **CPU-only** — не использовать NVENC/CUDA для ffmpeg
- Вернуть `output_path` при успехе, None при ошибке

#### 2. `src/slicr/utils/subtitles.py` — генерация субтитров

```python
def generate_srt(words: list[dict], output_path: str) -> str | None
def generate_ass(words: list[dict], output_path: str) -> str | None
```

**Формат входных данных (words):**
```python
[
    {"word": "привет", "start": 0.0, "end": 0.5},
    {"word": "мир", "start": 0.6, "end": 1.0},
    ...
]
```

**Требования для `generate_srt()` (прототип):**
- Группировать слова в строки по 5-7 слов или по 3 секунды (что раньше)
- Формат SRT:
  ```
  1
  00:00:00,000 --> 00:00:03,000
  привет мир как дела
  ```
- Вернуть `output_path` при успехе

**Требования для `generate_ass()` (прототип):**
- ASS формат с базовым стилем:
  - Шрифт: Arial Bold, размер 48
  - Цвет: белый с чёрной обводкой (BorderStyle=1, Outline=3)
  - Позиция: снизу по центру (Alignment=2, MarginV=50)
- Группировать слова так же как SRT (5-7 слов / 3 сек)
- Для прототипа **без** karaoke-эффекта (просто показ текста)
- Вернуть `output_path` при успехе

#### 3. `src/slicr/pipeline/editor.py` — VideoEditor

```python
class VideoEditor:
    def __init__(self, config: Config, db: Database) -> None
    async def create_clip(self, clip_id: int) -> str | None
```

**Требования:**
- `create_clip()`:
  1. `db.get_clip(clip_id)` → получить `video_id`, `start_time`, `end_time`
  2. `db.get_video(video_id)` → получить `file_path` (оригинальное видео)
  3. `db.get_transcription_by_video(video_id)` → получить `words_json`
  4. `db.update_clip_status(clip_id, VideoStatus.PROCESSING)`
  5. Создать пути:
     - `segment_path = config.temp_dir / f"segment_{clip_id}.mp4"`
     - `cropped_path = config.temp_dir / f"cropped_{clip_id}.mp4"`
     - `subtitle_path = config.clips_dir / f"clip_{clip_id}.ass"`
     - `final_path = config.clips_dir / f"clip_{clip_id}.mp4"`
  6. `extract_segment(file_path, segment_path, start_time, end_time)`
  7. `crop_to_vertical(segment_path, cropped_path)`
  8. Отфильтровать words_json: только слова в диапазоне [start_time, end_time], сдвинуть таймкоды на -start_time
  9. `generate_ass(filtered_words, subtitle_path)`
  10. Наложить субтитры через ffmpeg: `ffmpeg -i cropped_path -vf "ass=subtitle_path" -c:v libx264 -preset medium -crf 23 -c:a copy final_path`
  11. `db.update_clip_paths(clip_id, final_path, subtitle_path)`
  12. `db.update_clip_status(clip_id, VideoStatus.READY)`
  13. Удалить temp-файлы (segment, cropped)
  14. Вернуть `final_path`
- При ошибке: `VideoStatus.FAILED`, вернуть None
- Логировать каждый шаг

### Тесты:
Создать `tests/test_editor.py`:
- Тест generate_srt с mock-словами
- Тест generate_ass с mock-словами
- Тест что editor правильно фильтрует words по диапазону

### НЕ ТРОГАТЬ:
- `__main__.py`, `orchestrator.py`, любые `__init__.py`
- Файлы gpu/, services/, bot/
- Файлы pipeline кроме `editor.py`

---

## СЕССИЯ 0: Reviewer + Интеграция

### Промпт для запуска сессии:

```
Ты Opus-ревьюер проекта Slicr — автоматический видео-нарезчик.
Прочитай docs/PARALLEL_BUILD_PLAN.md — там описание всей параллельной работы.
Прочитай docs/CLAUDE.md, docs/MODULE_MAP.md, docs/DEVELOPMENT_WORKFLOW.md.

Твоя задача — ПОСЛЕ завершения сессий 1-3:
1. Мержить ветки feat/gpu-transcribe, feat/ai-publish, feat/editor в main
2. Разрешить конфликты если есть
3. Реализовать orchestrator.py — координатор всего pipeline
4. Обновить __main__.py — подключить все новые модули
5. Обновить все __init__.py с реэкспортами
6. Прогнать полный pytest
7. Код-ревью всех изменений (запустить code-reviewer агент)
```

### Работает в ветке: `main`

### Задачи:

#### 1. Merge веток
```bash
git merge feat/gpu-transcribe
git merge feat/ai-publish
git merge feat/editor
```

#### 2. `src/slicr/pipeline/orchestrator.py` — PipelineOrchestrator

```python
class PipelineOrchestrator:
    def __init__(self, config: Config, db: Database) -> None
    async def start(self) -> None
    async def stop(self) -> None
    async def process_video(self, video_id: int) -> None
```

**Требования:**
- `start()`: запускает 3 фоновых worker-а:
  - `_cpu_worker()` — обрабатывает JobType.SELECT и JobType.EDIT
  - `_gpu_worker()` — обрабатывает JobType.TRANSCRIBE (через GPUGuard)
  - `_publish_worker()` — обрабатывает JobType.PUBLISH
- Каждый worker — бесконечный цикл:
  ```python
  while self._running:
      job = await self.db.get_next_job(job_type, requires_gpu=...)
      if job:
          await self._process_job(job)
      else:
          await asyncio.sleep(5)
  ```
- `process_video()` — запускает полный цикл для одного видео:
  1. Создать job TRANSCRIBE
  2. (дальше worker-ы подхватят автоматически через цепочку)
- `stop()`: `self._running = False`, cancel задачи

#### 3. Обновить `__init__.py` файлы

- `pipeline/__init__.py`: реэкспорт всех классов
- `gpu/__init__.py`: реэкспорт GPUGuard, GPUWatchdog
- `services/__init__.py`: реэкспорт ClaudeClient, VKClipsClient, TelegramClientWrapper
- `utils/__init__.py`: реэкспорт функций

#### 4. Обновить `__main__.py`

Подключить все новые модули, инициализировать с правильным DI.

#### 5. Прогнать тесты + ревью

```bash
python -m pytest tests/ -x -q --timeout=120
```

Запустить code-reviewer агент на все изменённые файлы.

---

## ЦЕПОЧКА ЗАДАНИЙ В PIPELINE

После интеграции, полный цикл обработки одного видео:

```
Monitor обнаруживает видео в канале
  → db.add_video() + db.add_job(DOWNLOAD)

Downloader (уже работает) скачивает
  → db.update_video_status(DOWNLOADED)
  → db.add_job(TRANSCRIBE)

GPU Worker подхватывает TRANSCRIBE
  → GPUGuard.acquire()
  → WhisperTranscriber.transcribe(video_id) → transcription_id
  → GPUGuard.release()
  → db.add_job(SELECT, video_id)

CPU Worker подхватывает SELECT
  → MomentSelector.select_moment(video_id, transcription_id) → clip_id
  → db.add_job(EDIT, clip_id=clip_id)

CPU Worker подхватывает EDIT
  → VideoEditor.create_clip(clip_id) → final_path
  → Отправляет в tech_channel на модерацию (бот)

Модерация (уже работает)
  → Approve → db.add_job(PUBLISH, clip_id=clip_id)

Publish Worker подхватывает PUBLISH
  → ClipPublisher.publish_telegram(clip_id)
  → DONE
```

---

## ЧЕКЛИСТ ГОТОВНОСТИ ПРОТОТИПА

- [x] Monitor → Download: видео скачивается (Stage 2a-2c)
- [x] Claude API: ClaudeClient с CF Worker прокси, rate limiter, retry (2026-03-05)
- [x] AI Selection: MomentSelector вызывает Claude, сохраняет clip в БД (2026-03-05)
- [x] Cloudflare Worker: универсальный прокси /claude, /gemini, /groq (2026-03-05)
- [ ] Download → Transcribe: текст с таймкодами из whisper
- [ ] Select → Edit: ffmpeg кропает + накладывает субтитры
- [ ] Edit → Moderation: клип отправляется в tech-канал
- [ ] Moderation → Publish: после Approve публикуется в target-канал
- [ ] Mock-режим: весь цикл работает на Mac без GPU
- [ ] Orchestrator: worker-ы крутятся и подхватывают задачи

---

## ЗАВИСИМОСТИ ДЛЯ УСТАНОВКИ

```bash
# Сессия 1 (на Windows-машине с GPU):
pip install faster-whisper pynvml torch

# Сессия 2:
pip install anthropic

# Сессия 3:
# ffmpeg должен быть в PATH (системный)
pip install ffmpeg-python  # опционально, для удобства

# Все сессии:
pip install ruff pytest pytest-asyncio
```
