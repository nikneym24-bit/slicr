import logging
import logging.handlers
import os


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """
    Настраивает логирование для приложения.

    Консольный вывод: через WebSocketLogHandler (print + flush) в state.py.
    Файл: RotatingFileHandler на logger "slicr".
    """
    os.makedirs(log_dir, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    slicr_logger = logging.getLogger("slicr")
    slicr_logger.setLevel(numeric_level)
    slicr_logger.propagate = False

    # Идемпотентность: если file handler уже есть — не добавляем повторно
    has_file = any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        for h in slicr_logger.handlers
    )
    if not has_file:
        log_file = os.path.join(log_dir, "video-clipper.log")
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        slicr_logger.addHandler(file_handler)

