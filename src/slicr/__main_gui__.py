"""Точка входа GUI: python -m slicr.gui"""

import logging

from slicr.utils.logging_config import setup_logging


def main() -> None:
    """Запустить GUI-приложение Slicr."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Запуск Slicr GUI")

    from slicr.gui import SlicApp

    app = SlicApp()
    app.mainloop()


if __name__ == "__main__":
    main()
