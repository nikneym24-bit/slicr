#!/bin/bash
# dev.command — Video Clipper Dev Launcher
# Двойной клик в Finder для запуска

# Переход в корень проекта (scripts/ → video-clipper/)
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
python3 -m video_clipper

echo ""
read -p "Нажмите Enter для выхода..."
