# ЗАДАНИЕ: Этап 1.1 — Рефакторинг структуры проекта

## Роль
Ты — исполнитель. Архитектор принял решение перейти на `src/` layout. Твоя задача — перенести файлы ТОЧНО по схеме, обновить все импорты, убедиться что тесты проходят и main запускается.

## Проект
- Путь: `/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr/`
- Ветка: `stage-1/scaffolding` (ты на ней)
- Среда: macOS, Python 3.13, venv уже создан в `.venv/`

## Обязательно прочитай перед началом
- Текущую структуру проекта (все .py файлы)
- `docs/MODULE_MAP.md` — потом обновишь его

## Текущая структура (ПЛОСКАЯ, всё в корне)

```
slicr/
├── main.py
├── config.py
├── constants.py
├── requirements.txt
├── requirements-gpu.txt
├── creds.example.json
├── dev.command
├── README.md
├── .gitignore
├── .claudeignore
│
├── pipeline/            # Модули в корне
├── gpu/
├── database/
├── bot/
├── services/
├── utils/
├── tests/
├── docs/
├── storage/
└── .claude/
```

## Целевая структура (src/ layout)

```
slicr/
│
├── src/                            # Весь исполняемый код
│   └── slicr/              # Python-пакет
│       ├── __init__.py             # __version__ = "0.1.0"
│       ├── __main__.py             # Точка входа: python -m slicr
│       ├── config.py               # ← из корня
│       ├── constants.py            # ← из корня
│       │
│       ├── pipeline/               # ← из корня
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   ├── monitor.py
│       │   ├── downloader.py
│       │   ├── transcriber.py
│       │   ├── selector.py
│       │   ├── editor.py
│       │   └── publisher.py
│       │
│       ├── gpu/                    # ← из корня
│       │   ├── __init__.py
│       │   ├── guard.py
│       │   └── monitor.py
│       │
│       ├── database/               # ← из корня
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── models.py
│       │   └── migrations.py
│       │
│       ├── bot/                    # ← из корня
│       │   ├── __init__.py
│       │   ├── handlers.py
│       │   ├── moderation.py
│       │   └── keyboards.py
│       │
│       ├── services/               # ← из корня
│       │   ├── __init__.py
│       │   ├── claude_client.py
│       │   ├── vk_clips.py
│       │   └── telegram_client.py
│       │
│       └── utils/                  # ← из корня
│           ├── __init__.py
│           ├── video.py
│           ├── subtitles.py
│           └── logging_config.py
│
├── tests/                          # Остаётся в корне
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_database.py
│   └── test_config.py
│
├── docs/                           # Остаётся в корне
│   ├── CLAUDE.md
│   ├── MODULE_MAP.md
│   ├── CONTRIBUTING.md
│   ├── DEVELOPMENT_STANDARDS.md
│   └── PROMPTS/
│       ├── stage-1-scaffolding.md
│       └── stage-1.1-restructure.md
│
├── scripts/                        # НОВАЯ папка
│   └── dev.command                 # ← из корня
│
├── storage/                        # Остаётся
│   ├── downloads/.gitkeep
│   ├── clips/.gitkeep
│   └── temp/.gitkeep
│
├── .claude/                        # Остаётся
├── .gitignore
├── .claudeignore
├── README.md
├── requirements.txt
├── requirements-gpu.txt
├── creds.example.json
└── pyproject.toml                  # НОВЫЙ файл
```

---

## Пошаговый план

### Шаг 1: Создать pyproject.toml

```toml
[build-system]
requires = ["setuptools>=75.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "slicr"
version = "0.1.0"
description = "Автоматический конвейер видеоклипов: от Telegram-канала до VK Клипов"
requires-python = ">=3.13"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Шаг 2: Создать src/slicr/

```bash
mkdir -p src/slicr
```

### Шаг 3: Перенести модули

Перенести (git mv или обычный mv):
- `main.py` → `src/slicr/__main__.py`
- `config.py` → `src/slicr/config.py`
- `constants.py` → `src/slicr/constants.py`
- `pipeline/` → `src/slicr/pipeline/`
- `gpu/` → `src/slicr/gpu/`
- `database/` → `src/slicr/database/`
- `bot/` → `src/slicr/bot/`
- `services/` → `src/slicr/services/`
- `utils/` → `src/slicr/utils/`
- `dev.command` → `scripts/dev.command`

### Шаг 4: Создать src/slicr/__init__.py

```python
"""Video Clipper — автоматический конвейер видеоклипов."""

__version__ = "0.1.0"
```

### Шаг 5: Обновить __main__.py (бывший main.py)

Заменить все импорты с коротких на пакетные:

```python
# БЫЛО:
from config import load_config
from database import Database
from utils.logging_config import setup_logging
from pipeline.orchestrator import PipelineOrchestrator
# ...

# СТАЛО:
from slicr.config import load_config
from slicr.database import Database
from slicr.utils.logging_config import setup_logging
from slicr.pipeline.orchestrator import PipelineOrchestrator
# ...
```

### Шаг 6: Обновить ВСЕ внутренние импорты

Во всех файлах внутри `src/slicr/` заменить импорты:

| Было | Стало |
|------|-------|
| `from config import ...` | `from slicr.config import ...` |
| `from constants import ...` | `from slicr.constants import ...` |
| `from database import ...` | `from slicr.database import ...` |
| `from database.connection import ...` | `from slicr.database.connection import ...` |
| `from database.models import ...` | `from slicr.database.models import ...` |
| `from utils.logging_config import ...` | `from slicr.utils.logging_config import ...` |
| `from pipeline.* import ...` | `from slicr.pipeline.* import ...` |
| `from gpu.* import ...` | `from slicr.gpu.* import ...` |
| `from bot.* import ...` | `from slicr.bot.* import ...` |
| `from services.* import ...` | `from slicr.services.* import ...` |

**ВАЖНО:** Проверь КАЖДЫЙ .py файл. Используй grep чтобы найти все импорты.

### Шаг 7: Обновить тесты

В `tests/conftest.py`, `tests/test_database.py`, `tests/test_config.py`:

```python
# БЫЛО:
from database import Database
from config import Config, load_config, ConfigError

# СТАЛО:
from slicr.database import Database
from slicr.config import Config, load_config, ConfigError
```

### Шаг 8: Обновить scripts/dev.command

```bash
#!/bin/bash
# dev.command — Video Clipper Dev Launcher
# Двойной клик в Finder для запуска

# Переход в корень проекта (scripts/ → slicr/)
cd "$(dirname "$0")/.."

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

# Install project in editable mode (обеспечивает правильные импорты)
if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ] || [ pyproject.toml -nt .venv/.deps_installed ]; then
    echo "Устанавливаю зависимости..."
    pip install -q -r requirements.txt
    pip install -q -e .
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

# Запуск через пакет
python3 -m slicr

echo ""
read -p "Нажмите Enter для выхода..."
```

`chmod +x scripts/dev.command` после создания.

### Шаг 9: Обновить README.md

Обновить секцию запуска:
```
## Быстрый старт (macOS)

# Двойной клик по scripts/dev.command или:
./scripts/dev.command

# Или вручную:
pip install -e .
python -m slicr
```

### Шаг 10: Обновить .gitignore

Добавить:
```
# Editable install
*.egg-info/
src/*.egg-info/
```

### Шаг 11: Обновить .claudeignore

Заменить пути к модулям (если есть прямые ссылки).

### Шаг 12: Обновить ВСЮ документацию (ОБЯЗАТЕЛЬНО)

Согласно правилу целостности документации из CLAUDE.md, при структурном изменении ты ОБЯЗАН обновить все затронутые документы. Это рефакторинг всей структуры — затронуто ВСЁ.

**12.1. docs/MODULE_MAP.md** — ПОЛНОСТЬЮ переписать дерево проекта:
- Все пути теперь через `src/slicr/`
- Обновить каждую группу модулей — пути к файлам
- Обновить матрицу зависимостей
- Обновить секцию "Быстрый поиск"
- MODULE_MAP.md — это **утверждённая структура**, новые файлы создаются ТОЛЬКО по ней

**12.2. docs/CLAUDE.md** — обновить:
- Секция "Архитектура Проекта" — все пути через `src/slicr/`
- Секция "Dev-режим" — путь к dev.command теперь `scripts/dev.command`
- Примеры задач — пути к файлам
- НЕ трогать секции "Правило целостности документации" и "Правило утверждённой структуры" — они уже актуальны

**12.3. docs/CONTRIBUTING.md** — обновить:
- Секция "Быстрый старт" — путь к dev.command, команда запуска `python -m slicr`
- Секция "Запуск" — `python -m slicr` вместо `python3 main.py`
- Секция "Архитектура (кратко)" — ключевые модули с новыми путями
- Секция FAQ — обновить пути

**12.4. docs/DEVELOPMENT_STANDARDS.md** — обновить:
- Секция "Dev-режим" — путь к dev.command, команда запуска
- Секция "Структура проекта" — если есть ссылки на файлы

**12.5. .claude/agents/code-reviewer.md** — обновить:
- Секция "Context" — если есть ссылки на структуру

### Шаг 14: Удалить старые пустые директории

После переноса в корне НЕ должно остаться:
- `main.py`
- `config.py`
- `constants.py`
- `pipeline/`
- `gpu/`
- `database/`
- `bot/`
- `services/`
- `utils/`
- `dev.command` в корне

### Шаг 15: Переустановить и протестировать

```bash
cd "/Users/dvofis/Desktop/Програмирование/Завод-нарезчик видео /slicr"
source .venv/bin/activate
rm -f .venv/.deps_installed
pip install -e .
python -m pytest tests/ -v
SLICR_DEV=1 SLICR_MOCK_GPU=1 SLICR_MOCK_SELECTOR=1 timeout 3 python -m slicr; true
```

---

## Правила

1. **Пиши ТОЛЬКО код.** Не объясняй, не задавай вопросов.
2. Используй `git mv` для переноса файлов (сохраняет историю git).
3. Проверь КАЖДЫЙ .py файл на импорты — ни один старый импорт не должен остаться.
4. После переноса — тесты ОБЯЗАНЫ проходить (11/11).
5. `python -m slicr` с dev-флагами должен стартовать без ошибок.
6. `chmod +x scripts/dev.command` не забудь.
7. Не трогай содержимое docs/PROMPTS/ — это архив заданий.

## Критерии приёмки

### Код:
1. Все .py модули в `src/slicr/` — в корне проекта НЕТ ни одного .py модуля
2. `pyproject.toml` создан, `pip install -e .` работает
3. `python -m slicr` запускается в dev-режиме
4. `python -m pytest tests/ -v` — 11/11 passed
5. `scripts/dev.command` запускается (chmod +x)
6. Старые директории (pipeline/, gpu/, database/ и т.д.) удалены из корня

### Документация (ОБЯЗАТЕЛЬНО):
7. **docs/MODULE_MAP.md** — дерево проекта отражает НОВУЮ структуру src/slicr/, все пути актуальны
8. **docs/CLAUDE.md** — секция архитектуры обновлена с новыми путями
9. **docs/CONTRIBUTING.md** — команды запуска и пути обновлены
10. **docs/DEVELOPMENT_STANDARDS.md** — пути и команды обновлены
11. **README.md** — команды запуска обновлены
12. Ни в одном документе НЕТ ссылок на старые пути (main.py в корне, pipeline/ в корне и т.д.)
