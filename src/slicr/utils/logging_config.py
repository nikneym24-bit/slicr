import logging
import logging.handlers
import os


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """
    Настраивает логирование для приложения.

    Консоль: StreamHandler, формат [HH:MM:SS] LEVEL module — message
    Файл: logs/video-clipper.log, RotatingFileHandler (10 MB, 5 бэкапов)
    Формат файла: [YYYY-MM-DD HH:MM:SS] [LEVEL] [module] message

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Директория для файлов логов (создаётся если не существует)
    """
    os.makedirs(log_dir, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Убираем существующие handlers чтобы не дублировать при повторном вызове
    root_logger.handlers.clear()

    # --- Консольный handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(module)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # --- Файловый handler с ротацией ---
    log_file = os.path.join(log_dir, "video-clipper.log")
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
