# Contributing Guide

## Быстрый старт

### 1. Клонирование и настройка

```bash
git clone git@github.com:nikneym24-bit/slicr.git
cd slicr
```

### 2. Запуск в dev-режиме (macOS)

```bash
# Двойной клик по scripts/dev.command в Finder, или:
./scripts/dev.command
```

Скрипт автоматически:
- Создаст виртуальное окружение (.venv)
- Установит зависимости и пакет (pip install -e .)
- Создаст storage-директории
- Установит dev-переменные окружения
- Запустит python -m slicr

### 3. Ручная настройка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp creds.example.json creds.json
# Заполните свои данные в creds.json
```

### 4. Запуск

```bash
# Dev-режим (mock GPU, mock Selector)
SLICR_DEV=1 python -m slicr

# Production-режим (реальный GPU, реальный Claude API)
python -m slicr
```

---

## Обязательные стандарты

### Перед коммитом проверьте:

- [ ] Код соответствует [DEVELOPMENT_STANDARDS.md](DEVELOPMENT_STANDARDS.md)
- [ ] Нет дублирования кода (DRY principle)
- [ ] Используются enum-ы из `constants.py` (VideoStatus, JobStatus, ...)
- [ ] Добавлены type hints для новых функций
- [ ] Добавлено логирование (INFO для важных событий, ERROR для ошибок)
- [ ] Нет магических строк и чисел
- [ ] Mock-режим не сломан (scripts/dev.command работает на Mac)
- [ ] Тесты проходят: `python -m pytest tests/ -x -v`

### Формат коммитов

```
<тип>: <описание>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

**Типы:**
- `feat:` — Новая фича
- `fix:` — Исправление бага
- `refactor:` — Рефакторинг
- `docs:` — Документация
- `chore:` — Конфигурация, зависимости

**Примеры:**
```
feat: добавить транскрибацию через faster-whisper
fix: исправить кроп 9:16 для нестандартных разрешений
refactor: вынести GPU Guard в отдельный модуль
```

---

## Архитектура (кратко)

### Конвейер обработки

```
Telegram → Monitor → Downloader → Transcriber → Selector → Editor → Moderation → Publisher
                                     (GPU)       (Claude)   (ffmpeg)   (Bot)       (VK/TG)
```

### Ключевые модули

- `src/slicr/pipeline/orchestrator.py` — координатор конвейера
- `src/slicr/pipeline/transcriber.py` — транскрибация (faster-whisper)
- `src/slicr/pipeline/selector.py` — AI-отбор фрагмента (Claude API)
- `src/slicr/pipeline/editor.py` — монтаж (ffmpeg: кроп 9:16 + субтитры)
- `src/slicr/gpu/guard.py` — защита GPU от крашей оператора
- `src/slicr/bot/moderation.py` — inline-кнопки модерации
- `src/slicr/services/claude_client.py` — Claude API клиент

### Критически важно

- GPU (RTX 4060 Ti) разделяется с оператором → GPU Guard обязателен
- ffmpeg использует ТОЛЬКО CPU (не NVENC) — не занимаем GPU для кодирования
- Разработка на Mac → все GPU-модули имеют mock-режим
- Claude API mock в dev-режиме (фейковый structured output)

---

## Workflow

### Разработка по этапам (ветки)

```bash
# Этап 1: Scaffolding
git checkout stage-1/scaffolding

# Этап 2: Monitor + Downloader
git checkout -b stage-2/monitor-downloader

# и т.д.
```

### Создание новой фичи

```bash
git checkout -b feature/your-feature-name
# ... разработка
git add <specific files>
git commit -m "feat: описание фичи"
git push origin feature/your-feature-name
# Создать Pull Request
```

### Исправление бага

```bash
git checkout -b fix/bug-description
# ... исправление
git commit -m "fix: описание исправления"
git push origin fix/bug-description
```

---

## FAQ

### Почему два клиента Telegram (Telethon + Aiogram)?

- **Telethon (userbot)** — может читать любые каналы, мониторинг источников
- **Aiogram (bot)** — только боты могут отправлять inline-кнопки для модерации

### Где добавлять константы?

В `src/slicr/constants.py` в соответствующий StrEnum:
- `VideoStatus` — статусы видео в конвейере
- `JobType` — типы задач
- `JobStatus` — статусы задач
- `Platform` — платформы публикации

### Где добавлять новые методы БД?

В `src/slicr/database/models.py`. Методы автоматически доступны через `Database` класс.

### Как тестировать на Mac без GPU?

Установите переменные окружения:
```bash
export SLICR_DEV=1
export SLICR_MOCK_GPU=1
export SLICR_MOCK_SELECTOR=1
```

Или просто используйте `./scripts/dev.command`.

---

## Полезные ссылки

- **[DEVELOPMENT_STANDARDS.md](DEVELOPMENT_STANDARDS.md)** — полный гайд по стандартам
- **[MODULE_MAP.md](MODULE_MAP.md)** — карта модулей проекта
- **[CLAUDE.md](CLAUDE.md)** — инструкции для Claude
- **[../ARCHITECTURE.md](../../ARCHITECTURE.md)** — полная архитектура
- **[ROADMAP.md](ROADMAP.md)** — план развития
