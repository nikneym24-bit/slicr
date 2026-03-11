#!/bin/bash
# Деплой slicr на Windows PC и перезапуск сервиса
# Использование: ./scripts/deploy-win.sh [--reload]
#
# Скрипт: убивает процесс на порту 8080 → копирует файлы → создаёт start.bat.
# Запуск: пользователь кликает slicr.bat на рабочем столе Windows.

set -e

HOST="windows-pc"
REMOTE_DIR="C:\\slicr"
LOCAL_SRC="src/slicr"

echo "=== Деплой slicr на $HOST ==="

# 1. Убиваем все Python-процессы (освобождаем порт 8080)
echo "[1/3] Освобождаю порт 8080..."
# taskkill может не убить процессы из Session 0, поэтому убиваем через wmic
ssh $HOST "cmd /c wmic process where name=\"python.exe\" delete" 2>/dev/null || true
sleep 2

# 2. Копируем файлы
echo "[2/3] Копирую файлы..."
scp -r "$LOCAL_SRC/web/" "$HOST:${REMOTE_DIR}\\src\\slicr\\web\\"
scp "$LOCAL_SRC/__main_web__.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\__main_web__.py"
scp "$LOCAL_SRC/config.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\config.py"
scp "$LOCAL_SRC/services/processor.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\services\\processor.py"
scp "$LOCAL_SRC/services/transcription.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\services\\transcription.py"
scp "$LOCAL_SRC/services/claude_client.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\services\\claude_client.py"
scp "$LOCAL_SRC/utils/video.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\utils\\video.py"
scp "$LOCAL_SRC/utils/subtitles.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\utils\\subtitles.py"
scp "$LOCAL_SRC/utils/logging_config.py" "$HOST:${REMOTE_DIR}\\src\\slicr\\utils\\logging_config.py"

# 3. Создаём start.bat с нужными аргументами
ARGS="-m slicr.web"
if [ "$1" = "--reload" ]; then
    ARGS="$ARGS --reload"
    echo "[3/3] Создаю start.bat (с auto-reload)..."
else
    echo "[3/3] Создаю start.bat..."
fi

# Создаём bat локально и копируем на Windows
BAT_FILE=$(mktemp /tmp/slicr_start.XXXX.bat)
{
  echo '@echo off'
  echo 'title slicr web-service'
  echo 'cd /d C:\slicr'
  echo 'echo Освобождаю порт 8080...'
  echo 'taskkill /IM python.exe /F 2>nul'
  echo 'timeout /t 2 /nobreak >nul'
  echo 'set PYTHONUNBUFFERED=1'
  echo "C:\slicr\venv\Scripts\python.exe -u $ARGS"
  echo 'pause'
} > "$BAT_FILE"
# Конвертируем в CRLF (Windows line endings)
if command -v unix2dos &>/dev/null; then
    unix2dos -q "$BAT_FILE"
elif command -v sed &>/dev/null; then
    sed -i '' 's/$/\r/' "$BAT_FILE"
fi
scp "$BAT_FILE" "$HOST:C:\\slicr\\start.bat"
scp "$BAT_FILE" "$HOST:C:\\Users\\Videographer\\Desktop\\slicr.bat"
rm "$BAT_FILE"

# 4. Перезапускаем slicr на Windows в фоне
echo "[4/4] Запускаю slicr..."
ssh $HOST "Start-Process -WindowStyle Hidden -FilePath 'C:\slicr\venv\Scripts\python.exe' -ArgumentList '-u -m slicr.web $( [ "$1" = "--reload" ] && echo "--reload" )' -WorkingDirectory 'C:\slicr'" 2>/dev/null

# 5. Healthcheck
echo "[5/5] Healthcheck..."
sleep 5
for i in 1 2 3 4 5; do
    STATUS=$(ssh $HOST "curl.exe -s -o NUL -w '%{http_code}' --max-time 3 http://localhost:8080/api/health 2>NUL" 2>/dev/null)
    if [ "$STATUS" = "200" ]; then
        echo "=== Деплой завершён, slicr работает ==="
        exit 0
    fi
    sleep 3
done
echo "=== Деплой завершён, но healthcheck не прошёл — проверь логи ==="
