# Стандарты разработки

> **Версия:** 1.0
> **Последнее обновление:** 2026-02-23

---

## Бизнес-логика и архитектура

### Конвейер обработки видео

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ 1. МОНИТОР  │───>│ 2. ЗАГРУЗКА  │───>│ 3. ТРАНСКР. │───>│ 4. AI-ОТБОР  │───>│ 5. МОНТАЖ   │───>│ 6. МОДЕРАЦИЯ │
│ Telethon    │    │ Telegram API │    │ faster-     │    │ Claude API   │    │ ffmpeg      │    │ Telegram Bot │
│ каналы      │    │ видео→диск   │    │ whisper GPU │    │ лучший       │    │ кроп 9:16   │    │ Approve/     │
│ фильтр      │    │              │    │ word-level  │    │ фрагмент     │    │ субтитры    │    │ Reject       │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                                                                                                        │
                                                                                                  ┌─────▼──────┐
                                                                                                  │ 7. ПУБЛ.   │
                                                                                                  │ VK / TG    │
                                                                                                  └────────────┘
```

### Гибридный подход (Telethon + Aiogram)

1. **Telethon (userbot):**
   - Может читать ЛЮБЫЕ каналы
   - Мониторинг source-каналов
   - Скачивание видео

2. **Aiogram (bot):**
   - ТОЛЬКО боты могут отправлять inline-кнопки
   - Модерация клипов (Approve/Reject)
   - Команды управления

### Статусы видео

| Статус | Описание | Этап |
|--------|----------|------|
| `queued` | Обнаружено, ждёт скачивания | Monitor |
| `downloading` | Скачивается | Downloader |
| `downloaded` | Скачано на диск | Downloader |
| `transcribing` | Транскрибируется | Transcriber |
| `transcribed` | Транскрипция готова | Transcriber |
| `selecting` | AI выбирает момент | Selector |
| `selected` | Фрагмент выбран | Selector |
| `processing` | Монтаж (кроп + субтитры) | Editor |
| `ready` | Клип готов | Editor |
| `moderation` | На модерации | Bot |
| `approved` | Одобрен | Bot |
| `rejected` | Отклонён | Bot |
| `published` | Опубликован | Publisher |
| `failed` | Ошибка | Любой |
| `skipped` | Пропущен (нет речи / плохой момент) | Transcriber/Selector |

### GPU Guard — защита оператора

```
Приоритеты GPU:
  1. Оператор (графика)     — ВСЕГДА первый
  2. Наш pipeline (whisper)  — ТОЛЬКО когда GPU свободен
  3. Монтаж (ffmpeg)         — CPU-only, GPU НЕ используем
```

---

## Структура проекта

### Принципы организации файлов

1. **Один файл — одна ответственность**
   - `src/slicr/pipeline/transcriber.py` — только транскрибация
   - `src/slicr/pipeline/editor.py` — только монтаж
   - `src/slicr/bot/moderation.py` — только модерация

2. **Централизация общего кода**
   - Константы → `src/slicr/constants.py`
   - Клавиатуры → `src/slicr/bot/keyboards.py`
   - Внешние API → `src/slicr/services/`

3. **Mock-режим для разработки**
   - Каждый GPU-зависимый модуль имеет mock
   - Claude API → mock возвращает фейковый JSON
   - GPU Guard → mock всегда возвращает ALLOW

---

## Стандарты кода

### 1. Использование enum-ов

```python
# ПЛОХО — магические строки:
await db.update_video_status(video_id, 'transcribed')

# ХОРОШО — enum:
from slicr.constants import VideoStatus
await db.update_video_status(video_id, VideoStatus.TRANSCRIBED)
```

### 2. Type hints

```python
async def select_moment(
    transcription: str,
    segments: list[dict],
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> dict | None:
    """Выбор лучшего фрагмента через Claude API."""
    ...
```

### 3. Именование

| Тип | Стиль | Пример |
|-----|-------|--------|
| Переменные | `snake_case` | `video_id` |
| Функции | `snake_case` | `select_moment()` |
| Классы | `PascalCase` | `VideoStatus` |
| Константы | `UPPER_CASE` | `MAX_CLIP_DURATION` |
| Приватные | `_leading_underscore` | `_parse_segments()` |

### 4. Логирование

**Уровни:**
- `DEBUG` — детальная информация для отладки
- `INFO` — важные события (скачивание, транскрибация, публикация)
- `WARNING` — потенциальные проблемы (GPU занят, fallback на CPU)
- `ERROR` — ошибки, требующие внимания

```python
logger.info(f"Video #{video_id}: транскрибация завершена ({len(words)} слов)")
logger.warning(f"GPU занят оператором, ждём... (очередь: {queue_size})")
logger.error(f"Ошибка монтажа video #{video_id}: {e}")
```

### 5. Безопасность

- API ключи — только в `creds.json` (gitignore)
- Не показывать `str(e)` пользователю
- Санитизация captions из Telegram

---

## Работа с данными

### База данных (src/slicr/database/)

**Паттерн:** `ConnectionMixin` с кэшированным соединением.

```python
from slicr.database import Database

db = Database("slicr.db")
await db.init_tables()
```

**Правила:**
- Всегда `async with self._get_connection()`
- Транзакции автоматически: commit при успехе, rollback при ошибке
- PRAGMA: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`

### Дедупликация

Проверка по `(source_chat_id, source_message_id)` — UNIQUE constraint в таблице `videos`.

---

## Обработка ошибок

### Принципы

1. **Fail gracefully** — не крашить весь pipeline из-за одного видео
2. **Логировать всё** — каждая ошибка в логах
3. **Retry** — до 3 попыток с exponential backoff
4. **GPU safety** — при любой ошибке GPU → выгружаем модель из VRAM

### Паттерн обработки

```python
try:
    result = await process_video(video_id)
except GPUBusyError:
    logger.warning(f"GPU занят, video #{video_id} возвращается в очередь")
    await db.update_job_status(job_id, JobStatus.QUEUED)
except Exception as e:
    logger.error(f"Ошибка обработки video #{video_id}: {e}")
    await db.update_job_status(job_id, JobStatus.FAILED, error_message=str(e))
```

---

## Тестирование

### Приоритеты

1. **Высокий:** `src/slicr/database/`, `src/slicr/config.py`, `src/slicr/pipeline/selector.py`
2. **Средний:** `src/slicr/pipeline/editor.py`, `src/slicr/utils/`, `src/slicr/bot/moderation.py`
3. **Низкий:** Integration тесты

### Запуск тестов

```bash
python -m pytest tests/ -x -v
```

---

## Git Workflow

### Ветки по этапам

```
main
├── stage-1/scaffolding
├── stage-2/monitor-downloader
├── stage-3/transcriber
├── stage-4/selector
├── stage-5/editor
├── stage-6/orchestrator
├── stage-7/moderation-publisher
├── stage-8/gpu-guard
└── stage-9/deploy
```

### Коммиты

```
<тип>: <краткое описание>

<детальное описание (опционально)>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

---

## Dev-режим (macOS)

### Переменные окружения

| Переменная | Описание |
|-----------|----------|
| `SLICR_DEV=1` | Включает dev-режим |
| `SLICR_MOCK_GPU=1` | Mock GPU Guard (без pynvml) |
| `SLICR_MOCK_SELECTOR=1` | Mock Claude API |
| `SLICR_MOCK_MONITOR=1` | Не подключается к Telegram |

### Запуск

```bash
./scripts/dev.command   # Автоматически устанавливает все mock-флаги
```

---

**Последнее обновление:** 2026-02-23
