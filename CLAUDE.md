# Video Clipper — Инструкции для Claude

## ЯЗЫК ОБЩЕНИЯ

**Весь диалог с пользователем — на русском языке.**
Код, имена переменных, имена классов — на английском. Docstrings, комментарии, логи, коммит-сообщения, отчёты — на русском.

---

## Навигация

- **[docs/MODULE_MAP.md](docs/MODULE_MAP.md)** — карта всех модулей. Читай при структурных задачах, навигации в незнакомые пакеты или если затронуто 3+ модулей. Не нужен для точечных правок в одном файле.
- **[docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md)** — Orchestrator-Worker v3, роли моделей, порядок фаз.
- **[docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md)** — стандарты кода, статусы, паттерны.

---

## ГЛАВНОЕ ПРАВИЛО

**ВСЕГДА начинай работу с чтения [docs/MODULE_MAP.md](docs/MODULE_MAP.md)**

Этот файл содержит:
- Карту всех модулей проекта
- Группы модулей по функциональности
- Правила работы с файлами
- Типичные сценарии

## Протокол Работы

### При получении задачи:

1. Определи затронутые уровни и группы модулей (из контекста или MODULE_MAP)
2. Работай ТОЛЬКО с файлами из этих групп
3. Нужен файл вне группы — обоснуй необходимость

### 2. Примеры задач

**Задача:** "Исправить баг в транскрибации"
```
Активные группы:
   - ГРУППА 3 (Pipeline: Transcriber)
   - ГРУППА 4 (GPU Guard)
   - ГРУППА 6 (БД)

Читать:
   - src/slicr/pipeline/transcriber.py
   - src/slicr/gpu/guard.py, src/slicr/gpu/monitor.py
   - src/slicr/database/models.py (метод add_transcription)

НЕ читать:
   - src/slicr/pipeline/selector.py (не относится)
   - src/slicr/bot/* (не относится)
   - src/slicr/services/vk_clips.py (не относится)
```

**Задача:** "Улучшить AI-отбор фрагментов"
```
Активные группы:
   - ГРУППА 3 (Pipeline: Selector)
   - ГРУППА 5 (Services: claude_client)

Читать:
   - src/slicr/pipeline/selector.py
   - src/slicr/services/claude_client.py
   - docs/PROMPTS.md (промпты для Claude AI)

НЕ читать:
   - src/slicr/pipeline/editor.py (не относится)
   - src/slicr/gpu/* (Selector не использует GPU)
```

## Архитектура Проекта

### Конвейер (Pipeline)

```
Telegram → Monitor → Downloader → Transcriber → Selector → Editor → Moderation → Publisher
  (1)       (2)        (3)          (4)          (5)        (6)        (7)          (8)
```

### Ядро (Core)

```
src/slicr/__main__.py  # Точка входа: python -m slicr
src/slicr/config.py    # Загрузка конфигурации
src/slicr/constants.py # Константы (VideoStatus, JobType, JobStatus, Platform)

src/slicr/database/    # Пакет БД (aiosqlite)
├── __init__.py
├── connection.py              # _get_connection(), PRAGMA
├── models.py                  # CRUD: videos, transcriptions, clips, jobs, publications, sources, settings
└── migrations.py              # Автомиграции
```

### Pipeline (Конвейер обработки)

```
src/slicr/pipeline/
├── orchestrator.py           # Координатор: управляет очередью задач
├── monitor.py                # Мониторинг Telegram-каналов (Telethon)
├── downloader.py             # Скачивание видео из Telegram
├── transcriber.py            # Транскрибация (faster-whisper, GPU)
├── selector.py               # AI-отбор фрагмента (Claude API)
├── editor.py                 # Монтаж: кроп 9:16 + субтитры (ffmpeg)
└── publisher.py              # Публикация в VK Clips / Telegram
```

### GPU Guard (Защита GPU)

```
src/slicr/gpu/
├── guard.py                  # Pre-flight check + Gate Decision
└── monitor.py                # Runtime watchdog + VRAM мониторинг
```

### Bot (Telegram-бот)

```
src/slicr/bot/
├── handlers.py               # Команды: /start, /status, /sources
├── moderation.py             # Inline-кнопки модерации (Approve/Reject)
└── keyboards.py              # Клавиатуры
```

### Сервисы (Services)

```
src/slicr/services/
├── claude_client.py          # Claude API для AI-отбора
├── vk_clips.py               # VK Clips API
└── telegram_client.py        # Telethon-обёртка
```

### GUI (Десктопный интерфейс)

```
src/slicr/gui/
├── __init__.py               # Re-export SlicApp
├── app.py                    # Главное окно (CustomTkinter, 900x600)
├── update_dialog.py          # Диалог обновления (лаунчер-стиль)
├── workers.py                # ProcessingWorker (threading)
└── frames/
    ├── input_frame.py        # Выбор видеофайлов
    ├── settings_frame.py     # Настройки (кроп, субтитры, папка)
    ├── progress_frame.py     # Прогресс-бар + лог
    └── results_frame.py      # Результаты + открыть папку

src/slicr/__main_gui__.py    # Точка входа GUI: python -m slicr.gui
```

### Web (Веб-сервис)

```
src/slicr/web/
├── __init__.py               # Re-export create_app
├── __main__.py               # python -m slicr.web
├── app.py                    # FastAPI + статика + lifespan
├── state.py                  # AppState: очередь, воркер, WebSocket лог-стрим
├── routes.py                 # REST API: /process, /preview, /tasks, /download, /health
├── ws.py                     # WebSocket /ws/logs (реалтайм логи)
└── static/
    └── index.html            # Responsive UI (mobile + desktop), canvas crop preview

src/slicr/__main_web__.py    # Точка входа: python -m slicr.web → uvicorn 0.0.0.0:8080
```

#### API-эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | Healthcheck |
| POST | `/api/process` | Загрузить видео + запустить обработку (multipart/form-data) |
| POST | `/api/preview` | Извлечь кадр для превью кропа |
| GET | `/api/tasks` | Список всех задач |
| GET | `/api/tasks/{id}` | Статус задачи + список клипов |
| GET | `/api/download/{id}/{idx}` | Скачать готовый клип |
| WS | `/ws/logs` | Реалтайм логи обработки |

#### Деплой и запуск на Windows PC

```bash
# Деплой с MacBook (одна команда):
./scripts/deploy-win.sh            # обычный запуск
./scripts/deploy-win.sh --reload   # с auto-reload для разработки

# Ручной запуск на Windows:
cd C:\slicr
C:\slicr\venv\Scripts\python.exe -m slicr.web           # production
C:\slicr\venv\Scripts\python.exe -m slicr.web --reload   # dev (auto-reload .py/.html/.css/.js)

# Хранилище на Windows:
C:\slicr\storage\uploads\   # загруженные видео
C:\slicr\storage\clips\     # готовые клипы
```

#### Загрузка файлов

Загрузка видео — стриминговая (чанки по 1 МБ через aiofiles), не грузит весь файл в RAM.

#### Файрвол Windows

Порт 8080 и python.exe разрешены в Windows Firewall (правила: "Slicr Web 8080", "Slicr Python").

### Автообновление

```
src/slicr/updater.py          # AutoUpdater: GitHub Releases, фоновая проверка
.github/workflows/
└── build-release.yml         # CI/CD: сборка Windows .exe при пуше тега v*
```

### Утилиты (Utils)

```
src/slicr/utils/
├── video.py                  # ffmpeg-хелперы (кроп, нарезка, субтитры)
├── subtitles.py              # TikTok-субтитры (karaoke, pop-in, ASS)
└── logging_config.py         # Логирование (файл + консоль)
```

## Ключевые Сущности

- **Video** — исходное видео из Telegram-канала
- **Transcription** — транскрипция с таймкодами (word-level)
- **Clip** — нарезанный клип (выбранный AI фрагмент)
- **Job** — задача в очереди (download, transcribe, select, edit, publish)
- **Publication** — опубликованный клип (VK / Telegram)
- **Source** — канал-источник видео

## Статусы видео в конвейере

```
queued → downloading → downloaded → transcribing → transcribed → selecting → selected → processing → ready → moderation → approved/rejected → published
```

## Стек Технологий

- **Web:** FastAPI + uvicorn (веб-сервис на 0.0.0.0:8080)
- **WebSocket:** встроенный в FastAPI (реалтайм логи)
- **File I/O:** aiofiles (стриминговая загрузка файлов)
- **Bot Framework:** aiogram 3.x
- **Userbot:** telethon (мониторинг каналов)
- **Database:** SQLite + aiosqlite (async)
- **AI:** Claude API (отбор моментов)
- **STT:** Groq Whisper API (облачная транскрибация)
- **Video:** ffmpeg-python (нарезка, кроп, субтитры)
- **GUI:** CustomTkinter (десктопный интерфейс, legacy)
- **HTTP:** aiohttp (автообновление, API запросы)
- **GPU:** pynvml (мониторинг VRAM)
- **CI/CD:** GitHub Actions + PyInstaller (сборка .exe)
- **Testing:** pytest + pytest-asyncio

## Dev-режим (macOS)

Разработка ведётся на MacBook без NVIDIA GPU:

```
SLICR_DEV=1          — включает dev-режим
SLICR_MOCK_GPU=1     — mock GPU Guard (без pynvml)
SLICR_MOCK_SELECTOR=1 — mock Claude API (фейковый результат)
```

Запуск: двойной клик по `scripts/dev.command` или `python -m slicr`

### Деплой на Windows PC

```bash
./scripts/deploy-win.sh            # деплой + запуск
./scripts/deploy-win.sh --reload   # деплой + запуск с auto-reload
```

Скрипт: останавливает старый процесс → копирует файлы по SCP → запускает сервис → проверяет healthcheck.

## Серверы

### Продакшн-сервер (iMac)

Деплой и запуск production-версии — на iMac по SSH:

```
Хост:         192.168.0.147
Пользователь: erofejhabarov
Подключение:  ssh erofejhabarov@192.168.0.147
```

SSH-ключ MacBook уже добавлен в known_hosts. Для входа без пароля — настроить `ssh-copy-id`.

Софт устанавливается из GitHub Releases (скомпилированный .app/.dmg через CI/CD).

### Windows PC (рабочая станция + сервер)

Windows PC используется как рабочая станция (видеоредакторы) и сервер для Python веб-сервиса slicr.

```
Хост:         192.168.0.70
Пользователь: videographer (группа Administrators)
Подключение:  ssh windows-pc  (алиас в ~/.ssh/config)
              ssh videographer@192.168.0.70
ОС:           Windows 11 Pro (OpenSSH Server, shell: PowerShell)
Hostname:     DESKTOP-5PL6385
Спящий режим: отключён (экран гаснет через 10 мин)
GPU:          GTX 1660 Super (6 ГБ VRAM), CUDA 12.6
Удалённый доступ: RDP (Windows App на Mac), SSH (CLI)
Пароль Windows: 0000
```

**Установленный софт:**
- Python 3.13.12 (`C:\Users\Videographer\AppData\Local\Programs\Python\Python313\`)
- pip 25.3
- ffmpeg 8.0.1
- git 2.47.1 (`C:\Program Files\Git\cmd\git.exe`)
- RustDesk (удалённый рабочий стол)

SSH-ключ MacBook добавлен в `C:\ProgramData\ssh\administrators_authorized_keys`. Вход без пароля.

### Важные нюансы SSH на Windows

- Shell по умолчанию — **PowerShell**. Для обычных команд оборачивай в `cmd /c`:
  ```bash
  ssh windows-pc "cmd /c dir"         # через cmd
  ssh windows-pc "Get-ChildItem"      # через PowerShell
  ```
- PowerShell **не поддерживает `&&`** для цепочки команд. Используй `;` или отдельные SSH-вызовы
- Пути с пробелами — в кавычках: `"\"C:\\Program Files\\...\"`"
- Кодировка вывода — cp866 (кириллица будет кракозябрами в терминале Mac)

---

## Архитектурные правила: защита от гонок и дублирования

> Правила ниже основаны на опыте проекта TGForwardez, где отсутствие единых точек входа
> привело к 9 итерациям рефакторинга. Цель — не допустить тех же ошибок.

### Правило A: Единая точка смены статуса (State Machine)

**ВСЕ** изменения статусов (`videos.status`, `clips.status`, `jobs.status`) — ТОЛЬКО через
методы класса `Database` с валидацией допустимых переходов.

**ЗАПРЕЩЕНО:**
```python
# Прямой UPDATE статуса из pipeline-модуля:
await db.execute("UPDATE videos SET status = ? WHERE id = ?", (new_status, vid))  # НЕЛЬЗЯ
```

**ПРАВИЛЬНО:**
```python
# Через метод Database с валидацией:
await db.set_video_status(video_id, VideoStatus.DOWNLOADED, initiator="downloader")
```

Метод `set_video_status()` обязан:
1. Проверить допустимость перехода (state machine)
2. Обновить запись в БД
3. Записать событие в activity log (когда будет реализован)
4. Вернуть `bool` — успех или отказ

Допустимые переходы определяются в `constants.py` рядом с enum'ами статусов:
```python
VALID_VIDEO_TRANSITIONS: dict[VideoStatus, set[VideoStatus]] = {
    VideoStatus.QUEUED: {VideoStatus.DOWNLOADING},
    VideoStatus.DOWNLOADING: {VideoStatus.DOWNLOADED, VideoStatus.FAILED},
    VideoStatus.DOWNLOADED: {VideoStatus.TRANSCRIBING},
    # ... и так далее
}
```

### Правило B: Единый владелец разделяемых ресурсов

Каждый разделяемый ресурс имеет **ровно одного владельца**:

| Ресурс | Единственный владелец | Паттерн доступа |
|--------|----------------------|-----------------|
| Telethon client | `services/telegram_client.py` | Все модули получают клиент только через TelegramClientWrapper |
| GPU | `gpu/guard.py` | acquire/release перед и после whisper |
| Статусы сущностей | `database/models.py` | Только через `set_*_status()` с валидацией |
| Очередь задач | `pipeline/orchestrator.py` | Только orchestrator создаёт и назначает задачи |

**ЗАПРЕЩЕНО:** Создавать TelegramClient, менять статусы или управлять GPU вне указанных владельцев.

### Правило C: Все мутации через Database

Pipeline-модули **не пишут в БД напрямую через SQL**. Все мутации — через публичные методы
класса `Database` в `database/models.py`.

Это гарантирует:
- Синхронизацию памяти и БД
- Единую точку для валидации
- Возможность добавить activity log без изменения 10 файлов

### Правило D: Init barrier

При запуске приложения (`__main__.py`) фоновые задачи (monitor, orchestrator, bot)
**НЕ начинают работу** до завершения инициализации всех подсистем.

```python
init_complete = asyncio.Event()

# В monitor.run(), orchestrator.run():
await init_complete.wait()

# В __main__.py после инициализации БД, клиентов, конфига:
init_complete.set()
```

### Правило E: Нет прямого доступа к внутренним полям чужих модулей

```python
# ЗАПРЕЩЕНО — downloader лезет во внутренности monitor:
file_path = monitor._download_queue[0]._file_ref

# ПРАВИЛЬНО — через публичный API:
file_ref = await monitor.get_next_download()
```

Если публичного метода нет — добавь его во владельце, а не обходи инкапсуляцию.

---

## Фронтенд (Web UI)

Веб-интерфейс реализован как **single-page application** в одном файле `src/slicr/web/static/index.html`:

- **Фреймворк:** Vanilla JS + CSS (без фреймворков, минимальный стек)
- **Дизайн:** Тёмная тема, responsive (mobile + desktop)
- **Функции:** Drag & drop загрузка, canvas-превью кропа 9:16, настройки (кроп, субтитры, длительность), прогресс-бар + логи (WebSocket), скачивание готовых клипов
- **API-контракт:** REST (`/api/*`) + WebSocket (`/ws/logs`)
- **Статика:** Раздаётся FastAPI через `StaticFiles` + `FileResponse` для `/`

---

## Правило целостности документации

**При ЛЮБОМ структурном изменении проекта** (новые файлы, переименования, переносы, новые модули, изменение схемы БД, новые зависимости) ты ОБЯЗАН обновить ВСЮ затронутую документацию:

| Что изменилось | Какие документы обновить |
|---------------|------------------------|
| Новый .py файл или модуль | MODULE_MAP.md (дерево + группа), CLAUDE.md (секция архитектуры) |
| Переименование / перенос файла | MODULE_MAP.md, CLAUDE.md, CONTRIBUTING.md |
| Новая таблица в БД | MODULE_MAP.md (секция БД), ARCHITECTURE.md (секция 4) |
| Новая зависимость | requirements.txt или requirements-gpu.txt, CONTRIBUTING.md |
| Новая env-переменная | CLAUDE.md (секция Dev-режим), DEVELOPMENT_STANDARDS.md, dev.command |
| Новый статус/enum | constants.py, DEVELOPMENT_STANDARDS.md (таблица статусов) |
| Изменение конвейера | CLAUDE.md (секция Pipeline), MODULE_MAP.md, ARCHITECTURE.md |

**Порядок:**
1. Сделал изменение в коде
2. Обновил все затронутые документы из таблицы выше
3. Проверил что MODULE_MAP.md отражает ТЕКУЩЕЕ дерево проекта

**Если не уверен** — лучше обновить лишний документ, чем пропустить нужный.

---

## Правило утверждённой структуры

Структура проекта зафиксирована в **[docs/MODULE_MAP.md](docs/MODULE_MAP.md)** (секция "Архитектура Проекта").
Это **единственный источник истины** о том, где какие файлы лежат.

**ЗАПРЕЩЕНО:**
- Создавать .py файлы вне утверждённой структуры
- Создавать новые директории без согласования с архитектором
- Дублировать модули в разных местах

**Если нужен новый файл:**
1. Определи, к какой группе модулей он относится (MODULE_MAP.md)
2. Помести его в соответствующую директорию этой группы
3. Обнови MODULE_MAP.md — добавь файл в дерево и описание группы

**Правило роста модулей: файл → пакет**

Каждый модуль начинает жизнь как один .py файл. Когда модуль вырастает (>300 строк или появляются отдельные ответственности), он превращается в пакет (директорию):

```
# ДО: один файл
pipeline/editor.py              # class VideoEditor

# ПОСЛЕ: пакет с субмодулями
pipeline/editor/
├── __init__.py                 # re-export: from .crop import VideoEditor
├── crop.py                     # class VideoEditor (основной класс)
├── subtitles.py                # наложение субтитров
└── effects.py                  # zoom, transitions
```

**Обязательно:** `__init__.py` пакета реэкспортирует главный класс, чтобы внешние импорты НЕ ломались:
```python
# pipeline/editor/__init__.py
from slicr.pipeline.editor.crop import VideoEditor
__all__ = ["VideoEditor"]

# Весь остальной код продолжает работать без изменений:
from slicr.pipeline.editor import VideoEditor
```

---

## Правила архитектуры кода

### Правило 1: Только абсолютные импорты

Во всех файлах проекта используются **только абсолютные импорты**:

```python
# ПРАВИЛЬНО:
from slicr.config import load_config
from slicr.constants import VideoStatus
from slicr.database import Database

# ЗАПРЕЩЕНО:
from .models import Database          # относительный импорт
from ..constants import VideoStatus   # относительный импорт
```

**Единственное исключение:** `__init__.py` пакета может использовать относительный импорт для реэкспорта:
```python
# database/__init__.py — допустимо:
from .models import Database
```

**Почему:** При переносе файла нужно обновить только его импорты, а не все файлы, которые от него зависят.

### Правило 2: Направление зависимостей

Модули могут импортировать **только вниз по иерархии**, никогда вверх или поперёк:

```
Уровень 0 (общее):   constants.py, config.py
Уровень 1 (данные):  database/
Уровень 2 (сервисы): services/, utils/, gpu/
Уровень 3 (логика):  pipeline/
Уровень 4 (UI):      bot/, gui/, web/
Уровень 5 (запуск):  __main__.py, __main_gui__.py, __main_web__.py
```

**ЗАПРЕЩЕНО:**
| Модуль | НЕ может импортировать из |
|--------|--------------------------|
| `utils/` | pipeline/, bot/, services/, gpu/ |
| `services/` | pipeline/, bot/ |
| `database/` | pipeline/, bot/, services/, gpu/ |
| `pipeline/` | bot/ |
| `gpu/` | pipeline/, bot/, services/ |

**Если нужна обратная связь** — через callback, event или database.

### Правило 3: Публичный API через `__init__.py`

Каждый пакет определяет свой публичный API в `__init__.py` через `__all__`:

```python
# services/__init__.py
from slicr.services.claude_client import ClaudeClient
from slicr.services.vk_clips import VKClipsClient
from slicr.services.telegram_client import TelegramClientWrapper
__all__ = ["ClaudeClient", "VKClipsClient", "TelegramClientWrapper"]
```

**Внешний код импортирует из пакета, не из внутренних модулей:**
```python
# ПРЕДПОЧТИТЕЛЬНО:
from slicr.services import ClaudeClient

# ДОПУСТИМО, но при рефакторинге может сломаться:
from slicr.services.claude_client import ClaudeClient
```

### Правило 4: Изоляция внешних библиотек

Все обращения к внешним API — **только через `services/`**. Код pipeline/, bot/ и остальных модулей **не импортирует** внешние SDK напрямую:

```python
# ПРАВИЛЬНО — pipeline/selector.py:
from slicr.services import ClaudeClient
result = await claude_client.select_moment(transcription)

# ЗАПРЕЩЕНО — pipeline/selector.py:
import anthropic  # Прямой импорт внешнего SDK
client = anthropic.AsyncAnthropic()
```

**Почему:** Если завтра поменяем Claude на другой AI — меняем 1 файл в services/, а не 10 файлов по проекту.

**Исключения:** Общие утилиты (aiosqlite в database/, ffmpeg-python в utils/) — это их прямая ответственность.

### Правило 5: Pipeline-модули независимы

Модули внутри `pipeline/` **не импортируют друг друга**. Связь между этапами — только через БД и orchestrator:

```python
# ЗАПРЕЩЕНО — pipeline/editor.py:
from slicr.pipeline.selector import SelectorResult  # Прямая связь!

# ПРАВИЛЬНО — pipeline/editor.py:
from slicr.database import Database
clip = await db.get_clip(clip_id)  # Данные из БД
```

**Почему:** Каждый этап конвейера — независимый блок. Можно заменить, отключить или переписать любой этап, не трогая остальные.

**Единственное исключение:** `orchestrator.py` может импортировать все pipeline-модули — это его задача.

---

## После написания кода — ОБЯЗАТЕЛЬНАЯ проверка

```bash
# 1. Линтер на изменённые файлы
ruff check src/slicr/path/to/changed_file.py

# 2. Релевантные тесты
pytest tests/test_relevant.py -x -q --timeout=60

# 3. Полный прогон (перед коммитом)
pytest tests/ -x -q --timeout=120
```

**Если ruff или тесты падают — починить перед коммитом. Не коммитить сломанный код.**

---

## Параллельность

**Всегда запускай параллельных агентов** когда задачи независимы. Примеры:
- Ревью 4 модулей → 4 параллельных агента (не последовательно)
- Исследование 3 файлов → 3 параллельных Read/Grep
- Фикс в разных пакетах → параллельные worker-агенты

Не жди завершения одного агента, чтобы запустить следующий, если между ними нет зависимости.

Подробнее о фазах работы агентов — см. [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md).

---

## Важные Правила

### ДЕЛАЙ:
1. Читай MODULE_MAP.md перед каждой задачей
2. Определяй активные группы модулей
3. Работай только с релевантными файлами
4. Используй `src/slicr/database/` и `src/slicr/constants.py` (они общие)
5. Учитывай dev-режим: все GPU-зависимые модули имеют mock
6. **Обновляй документацию при каждом структурном изменении**
7. **Все мутации статусов — через Database с валидацией (Правило A)**
8. **Все ресурсы — через единого владельца (Правило B)**

### НЕ ДЕЛАЙ:
1. Не читай все файлы подряд
2. Не открывай тесты без необходимости
3. Не смотри vk_clips.py при работе с транскрибацией
4. Не открывай файлы "на всякий случай"
5. Не ломай mock-режим — он нужен для разработки на Mac
6. **Не создавай файлы вне утверждённой структуры (MODULE_MAP.md)**
7. **Не забывай обновлять доку при изменениях**
8. **Не используй относительные импорты** (см. Правило 1)
9. **Не создавай циклические зависимости между модулями** (см. Правило 2)
10. **Не импортируй внешние SDK напрямую из pipeline/bot/** (см. Правило 4)
11. **Не меняй статусы напрямую через SQL — только через Database методы** (см. Правило A)
12. **Не создавай TelegramClient / не управляй GPU вне назначенного владельца** (см. Правило B)

### СПРАШИВАЙ:
- Если нужен файл вне активной группы — объясни ЗАЧЕМ
- Если не уверен в группе модулей — уточни
- **Если нужна новая директория — согласуй с архитектором**

## Соглашения

- Async/await для всех операций
- Типизация через typing + StrEnum
- Логирование через logging (не print)
- Тесты в pytest
- Commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Python 3.13+

## Дополнительная Документация

- **[docs/MODULE_MAP.md](docs/MODULE_MAP.md)** — главная карта модулей и утверждённая структура (ОБЯЗАТЕЛЬНА К ПРОЧТЕНИЮ)
- **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** — гайд по разработке
- **[docs/DEVELOPMENT_STANDARDS.md](docs/DEVELOPMENT_STANDARDS.md)** — стандарты кода
- **[docs/PARALLEL_BUILD_PLAN.md](docs/PARALLEL_BUILD_PLAN.md)** — план параллельной сборки
- **[docs/TGF_INTEGRATION.md](docs/TGF_INTEGRATION.md)** — интеграция с TGForwardez

---

**ПОМНИ:** MODULE_MAP.md — единственный источник истины о структуре проекта!
