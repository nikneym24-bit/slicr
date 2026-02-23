# Карта Модулей Проекта

> **Для Claude:** При получении задачи используйте эту карту чтобы определить какие модули нужны для её выполнения. **ВАЖНО:** Запрашивайте файлы ТОЛЬКО из релевантных групп модулей.

## Принцип работы

1. **Идентифицируй задачу** → Определи к какой области она относится
2. **Найди группу модулей** → Используй эту карту для поиска нужной группы
3. **Работай только с релевантными файлами** → Не читай ничего лишнего
4. **Нужен файл вне группы?** → Обоснуй необходимость перед чтением

---

## Архитектура Проекта

```
video-clipper/
│
├─ pyproject.toml                         # Конфигурация проекта, зависимости
├─ creds.example.json                     # Шаблон конфига
│
├─ src/video_clipper/                     # Основной пакет
│  ├─ __init__.py                         # Инициализация пакета
│  ├─ __main__.py                         # Точка входа (python -m video_clipper)
│  ├─ config.py                           # Загрузка конфигурации (creds.json + env)
│  ├─ constants.py                        # Enum-ы: VideoStatus, JobType, JobStatus, Platform
│  │
│  ├─ database/                           # Пакет БД (aiosqlite)
│  │  ├─ __init__.py
│  │  ├─ connection.py                      # ConnectionMixin, PRAGMA настройки
│  │  ├─ models.py                          # CRUD для 7 таблиц
│  │  └─ migrations.py                      # Автомиграции
│  │
│  ├─ pipeline/                           # Конвейер обработки
│  │  ├─ orchestrator.py                    # Координатор: CPU/GPU/Moderation очереди
│  │  ├─ monitor.py                         # Мониторинг Telegram-каналов (Telethon)
│  │  ├─ downloader.py                      # Скачивание видео
│  │  ├─ transcriber.py                     # STT: faster-whisper (GPU)
│  │  ├─ selector.py                        # AI-отбор: Claude API
│  │  ├─ editor.py                          # Монтаж: ffmpeg (кроп 9:16 + субтитры)
│  │  └─ publisher.py                       # Публикация: VK Clips + Telegram
│  │
│  ├─ gpu/                                # Управление GPU
│  │  ├─ guard.py                           # GPU Guard: pre-flight + gate decision
│  │  └─ monitor.py                         # Watchdog: VRAM, процессы, температура
│  │
│  ├─ bot/                                # Telegram-бот
│  │  ├─ handlers.py                        # Команды: /start, /status, /sources
│  │  ├─ moderation.py                      # Inline-кнопки: Approve/Reject
│  │  └─ keyboards.py                       # Генерация клавиатур
│  │
│  ├─ services/                           # Внешние сервисы
│  │  ├─ claude_client.py                   # Claude API клиент
│  │  ├─ vk_clips.py                        # VK Clips API
│  │  └─ telegram_client.py                 # Telethon-обёртка
│  │
│  └─ utils/                              # Утилиты
│     ├─ video.py                           # ffmpeg-хелперы
│     ├─ subtitles.py                       # Генерация субтитров
│     └─ logging_config.py                  # Настройка логирования
│
├─ scripts/
│  └─ dev.command                         # macOS лаунчер
│
├─ tests/                                 # Тесты (в корне проекта)
│  ├─ conftest.py
│  ├─ test_database.py
│  ├─ test_config.py
│  └─ test_pipeline.py
│
├─ docs/                                  # Документация (в корне проекта)
│
└─ storage/                               # Хранилище, gitignore (в корне проекта)
   ├─ downloads/                            # Скачанные видео
   ├─ clips/                                # Готовые клипы
   └─ temp/                                 # Промежуточные файлы
```

---

## Группы Модулей

### ГРУППА 1: Конфигурация и Запуск

**Когда использовать:**
- Настройка проекта, конфиги, запуск
- Dev-режим, mock-флаги
- Переменные окружения

**Файлы:**
```
pyproject.toml                          # Конфигурация проекта, зависимости
src/video_clipper/__init__.py           # Инициализация пакета
src/video_clipper/__main__.py           # Точка входа (python -m video_clipper)
src/video_clipper/config.py             # Загрузка creds.json + env
src/video_clipper/constants.py          # Enum-ы и константы
scripts/dev.command                     # macOS лаунчер
creds.example.json                      # Шаблон конфига
```

**Зависимости:** Нет

---

### ГРУППА 2: База Данных

**Когда использовать:**
- CRUD операции с видео/клипами/задачами
- Изменение схемы БД
- Миграции, дедупликация

**Файлы:**
```
src/video_clipper/database/
├── __init__.py          # Класс Database
├── connection.py        # ConnectionMixin, PRAGMA (WAL, foreign_keys)
├── models.py            # CRUD: videos, transcriptions, clips, jobs, publications, sources, settings
└── migrations.py        # Автомиграции (schema_version)
```

**Таблицы:**
- `videos` — исходные видео (включает `buffer_message_id` — ID пересланного сообщения в Buffer)
- `transcriptions` — транскрипции (word-level)
- `clips` — нарезанные клипы
- `jobs` — очередь задач
- `publications` — публикации (VK, Telegram)
- `sources` — каналы-источники
- `settings` — key-value конфигурация

**Зависимости:** aiosqlite

---

### ГРУППА 3: Pipeline (Конвейер)

**Когда использовать:**
- Обработка видео от начала до конца
- Конкретный этап конвейера
- Координация этапов

**Файлы:**
```
src/video_clipper/pipeline/
├── orchestrator.py      # Координатор: CPU/GPU/Moderation очереди
├── monitor.py           # Telethon: слушает каналы, фильтр видео >= 30 сек
├── downloader.py        # Скачивание видео из Telegram
├── transcriber.py       # faster-whisper: word-level timestamps, VAD
├── selector.py          # Claude API: выбор лучшего фрагмента 15-60 сек
├── editor.py            # ffmpeg: кроп 9:16, субтитры, H.264 CPU-only
└── publisher.py         # VK Clips API + Telegram Bot API
```

**Зависимости:** `src/video_clipper/database/`, `src/video_clipper/gpu/`, `src/video_clipper/services/`, `src/video_clipper/utils/`

---

### ГРУППА 4: GPU Guard

**Когда использовать:**
- Управление GPU-ресурсами
- Защита от крашей оператора
- Mock-режим для Mac

**Файлы:**
```
src/video_clipper/gpu/
├── guard.py             # Pre-flight check: VRAM, процессы, utilization
└── monitor.py           # Watchdog: мониторинг каждые 2 сек во время whisper
```

**Ключевое:**
- RTX 4060 Ti (8 GB) — разделяемый ресурс с оператором-графиком
- mock-режим на Mac (VIDEO_CLIPPER_MOCK_GPU=1)
- ALLOW: свободно > 3 GB + нет GPU-процессов + utilization < 30%
- ABORT: VRAM < 1 GB во время работы → прерываем

**Зависимости:** pynvml (опционально)

---

### ГРУППА 5: Внешние Сервисы

**Когда использовать:**
- Claude API (AI-отбор)
- VK Clips API (публикация)
- Telethon (мониторинг каналов)

**Файлы:**
```
src/video_clipper/services/
├── claude_client.py     # Claude API: structured output, JSON schema
├── vk_clips.py          # VK Clips API: загрузка короткого видео
└── telegram_client.py   # Telethon: подключение, session management
```

**Зависимости:** anthropic, vk_api, telethon

---

### ГРУППА 6: Telegram Bot

**Когда использовать:**
- Команды бота (/start, /status)
- Модерация клипов (Approve/Reject)
- Клавиатуры и inline-кнопки

**Файлы:**
```
src/video_clipper/bot/
├── handlers.py          # Команды: /start, /help, /status, /sources
├── moderation.py        # Inline-кнопки: Approve/Reject/Edit/Schedule
└── keyboards.py         # Генерация InlineKeyboardMarkup
```

**Зависимости:** aiogram, `src/video_clipper/database/`

---

### ГРУППА 7: Утилиты

**Когда использовать:**
- ffmpeg-обработка видео
- Генерация субтитров
- Настройка логирования

**Файлы:**
```
src/video_clipper/utils/
├── video.py             # ffmpeg-python: кроп, конкат, кодеки
├── subtitles.py         # ASS/SRT генерация, word-by-word
└── logging_config.py    # setup_logging(): файл + консоль, ротация
```

**Зависимости:** ffmpeg-python

---

### ГРУППА 8: Тесты

**Когда использовать:**
- Написание/запуск тестов
- CI/CD

**Файлы:**
```
tests/
├── conftest.py          # Фикстуры pytest
├── test_database.py     # Тесты БД
├── test_config.py       # Тесты конфига
├── test_stage2a.py      # Тесты Stage 2a: Monitor + TelegramClient
├── test_stage2b.py      # Тесты Stage 2b: Bot + модерация
└── test_stage2c.py      # Тесты Stage 2c: VideoDownloader
```

**Зависимости:** pytest, pytest-asyncio

---

## Типичные Сценарии Работы

### Сценарий 1: "Транскрибация работает некорректно"
**Активные группы:**
- ГРУППА 3 (Pipeline: transcriber.py)
- ГРУППА 4 (GPU Guard)
- ГРУППА 2 (БД: transcriptions)

### Сценарий 2: "AI выбирает плохие моменты"
**Активные группы:**
- ГРУППА 3 (Pipeline: selector.py)
- ГРУППА 5 (Services: claude_client.py)

### Сценарий 3: "Субтитры отображаются криво"
**Активные группы:**
- ГРУППА 3 (Pipeline: editor.py)
- ГРУППА 7 (Utils: subtitles.py, video.py)

### Сценарий 4: "Кнопка Approve не работает"
**Активные группы:**
- ГРУППА 6 (Bot: moderation.py)
- ГРУППА 3 (Pipeline: publisher.py)
- ГРУППА 2 (БД: clips, publications)

### Сценарий 5: "Добавить новый источник видео"
**Активные группы:**
- ГРУППА 3 (Pipeline: monitor.py)
- ГРУППА 6 (Bot: handlers.py)
- ГРУППА 2 (БД: sources)

---

## Матрица Зависимостей

| Модуль | Зависит от |
|--------|------------|
| src/video_clipper/pipeline/orchestrator.py | src/video_clipper/database/, src/video_clipper/gpu/, src/video_clipper/pipeline/* |
| src/video_clipper/pipeline/monitor.py | src/video_clipper/database/, src/video_clipper/services/telegram_client.py |
| src/video_clipper/pipeline/downloader.py | src/video_clipper/database/, src/video_clipper/services/telegram_client.py |
| src/video_clipper/pipeline/transcriber.py | src/video_clipper/database/, src/video_clipper/gpu/ |
| src/video_clipper/pipeline/selector.py | src/video_clipper/database/, src/video_clipper/services/claude_client.py |
| src/video_clipper/pipeline/editor.py | src/video_clipper/database/, src/video_clipper/utils/video.py, src/video_clipper/utils/subtitles.py |
| src/video_clipper/pipeline/publisher.py | src/video_clipper/database/, src/video_clipper/services/vk_clips.py, src/video_clipper/bot/ |
| src/video_clipper/gpu/* | pynvml (опционально) |
| src/video_clipper/bot/* | aiogram, src/video_clipper/database/ |
| src/video_clipper/services/claude_client.py | anthropic |
| src/video_clipper/services/vk_clips.py | vk_api |
| src/video_clipper/services/telegram_client.py | telethon |
| src/video_clipper/__main__.py | ВСЁ |

---

## Быстрый Поиск

### По функционалу:
- **Конфиг и запуск** → ГРУППА 1
- **База данных** → ГРУППА 2
- **Конвейер (pipeline)** → ГРУППА 3
- **GPU** → ГРУППА 4
- **Внешние API** → ГРУППА 5
- **Telegram бот** → ГРУППА 6
- **Утилиты** → ГРУППА 7
- **Тесты** → ГРУППА 8

### По этапу конвейера:
- Мониторинг каналов → `src/video_clipper/pipeline/monitor.py` + `src/video_clipper/services/telegram_client.py`
- Скачивание → `src/video_clipper/pipeline/downloader.py`
- Транскрибация → `src/video_clipper/pipeline/transcriber.py` + `src/video_clipper/gpu/*`
- AI-отбор → `src/video_clipper/pipeline/selector.py` + `src/video_clipper/services/claude_client.py`
- Монтаж → `src/video_clipper/pipeline/editor.py` + `src/video_clipper/utils/video.py` + `src/video_clipper/utils/subtitles.py`
- Модерация → `src/video_clipper/bot/moderation.py` + `src/video_clipper/bot/keyboards.py`
- Публикация → `src/video_clipper/pipeline/publisher.py` + `src/video_clipper/services/vk_clips.py`

---

**Версия:** 2.0
**Последнее обновление:** 2026-02-23
