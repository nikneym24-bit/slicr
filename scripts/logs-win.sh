#!/bin/bash
# Реалтайм логи с Windows PC через WebSocket
# Использование: ./scripts/logs-win.sh [host:port]
#
# Требует: pip install websocket-client (или brew install websocat)

HOST="${1:-192.168.0.70:8080}"
WS_URL="ws://${HOST}/ws/logs"

echo "=== Подключение к логам slicr: $WS_URL ==="
echo "    Ctrl+C для выхода"
echo ""

# Пробуем websocat (быстрее, без Python)
if command -v websocat &>/dev/null; then
    websocat "$WS_URL"
    exit $?
fi

# Фолбэк на Python
python3 -c "
import asyncio, signal, sys

async def main():
    try:
        import websockets
    except ImportError:
        print('Установи: pip install websockets')
        print('Или:      brew install websocat')
        sys.exit(1)

    uri = '$WS_URL'
    try:
        async with websockets.connect(uri) as ws:
            async for msg in ws:
                print(msg, flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'Ошибка: {e}', file=sys.stderr)
        sys.exit(1)

asyncio.run(main())
"
