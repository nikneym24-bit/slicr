# Video Clipper — Инструкции для Claude

## ЯЗЫК ОБЩЕНИЯ

**Весь диалог с пользователем — на русском языке.**
Код, имена переменных, имена классов — на английском. Docstrings, комментарии, логи, коммит-сообщения, отчёты — на русском.

---

## ГЛАВНОЕ ПРАВИЛО

**ВСЕГДА начинай работу с чтения [MODULE_MAP.md](MODULE_MAP.md)**

Этот файл содержит:
- Карту всех модулей проекта
- Группы модулей по функциональности
- Правила работы с файлами
- Типичные сценарии

## Протокол Работы

### 1. Получил задачу
```
1. Прочитай MODULE_MAP.md
2. Определи активные группы модулей
3. Работай ТОЛЬКО с файлами из этих групп
4. Нужен файл вне группы? → Обоснуй необходимость
```

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

src/slicr/database/    # Пакет БД (aiosqlite, миксины)
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

### Утилиты (Utils)

```
src/slicr/utils/
├── video.py                  # ffmpeg-хелперы (кроп, конкат, кодеки)
├── subtitles.py              # Генерация и рендеринг субтитров
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

- **Bot Framework:** aiogram 3.x
- **Userbot:** telethon (мониторинг каналов)
- **Database:** SQLite + aiosqlite (async)
- **AI:** Claude API (отбор моментов)
- **STT:** faster-whisper (транскрибация на GPU)
- **Video:** ffmpeg-python (нарезка, кроп, субтитры)
- **GPU:** pynvml (мониторинг VRAM)
- **Testing:** pytest + pytest-asyncio

## Dev-режим (macOS)

Разработка ведётся на MacBook без NVIDIA GPU:

```
SLICR_DEV=1          — включает dev-режим
SLICR_MOCK_GPU=1     — mock GPU Guard (без pynvml)
SLICR_MOCK_SELECTOR=1 — mock Claude API (фейковый результат)
```

Запуск: двойной клик по `scripts/dev.command` или `python -m slicr`

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

Структура проекта зафиксирована в **MODULE_MAP.md** (секция "Архитектура Проекта").
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
Уровень 4 (UI):      bot/
Уровень 5 (запуск):  __main__.py
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

## Важные Правила

### ДЕЛАЙ:
1. Читай MODULE_MAP.md перед каждой задачей
2. Определяй активные группы модулей
3. Работай только с релевантными файлами
4. Используй `src/slicr/database/` и `src/slicr/constants.py` (они общие)
5. Учитывай dev-режим: все GPU-зависимые модули имеют mock
6. **Обновляй документацию при каждом структурном изменении**

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

- **[MODULE_MAP.md](MODULE_MAP.md)** — главная карта модулей и утверждённая структура (ОБЯЗАТЕЛЬНА К ПРОЧТЕНИЮ)
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — гайд по разработке
- **[DEVELOPMENT_STANDARDS.md](DEVELOPMENT_STANDARDS.md)** — стандарты кода
- **[../ARCHITECTURE.md](../../ARCHITECTURE.md)** — полная архитектура
- **[ROADMAP.md](ROADMAP.md)** — план развития

---

**ПОМНИ:** MODULE_MAP.md — единственный источник истины о структуре проекта!
