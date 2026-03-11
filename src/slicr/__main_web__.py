"""
Точка входа веб-сервиса: python -m slicr.web

Запускает FastAPI на 0.0.0.0:8080 (доступен по локальной сети).
С --reload отслеживает изменения файлов и перезагружается автоматически.
"""

import logging
import os
import sys
from pathlib import Path

import uvicorn

from slicr.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# Корень проекта: 3 уровня вверх от slicr/__main_web__.py → src/slicr/
SRC_DIR = str(Path(__file__).resolve().parent.parent)


def main() -> None:
    reload = "--reload" in sys.argv or os.environ.get("SLICR_DEV") == "1"

    logger.info("Запуск slicr web-service на http://0.0.0.0:8080 (reload=%s)", reload)

    if reload:
        logger.info("Reload-директория: %s", SRC_DIR)
        # В reload-режиме передаём строку, не объект
        uvicorn.run(
            "slicr.web.app:create_app",
            factory=True,
            host="0.0.0.0",
            port=8080,
            log_level="info",
            reload=True,
            reload_dirs=[SRC_DIR],
            reload_includes=["*.py", "*.html", "*.css", "*.js"],
        )
    else:
        from slicr.web.app import create_app
        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
