"""
Утилиты для работы с видео через ffmpeg-python.

Хелперы для нарезки фрагментов, кропа в вертикальный формат 9:16,
конкатенации и кодирования.

Реализация: этап 2.
"""

import logging

logger = logging.getLogger(__name__)


async def crop_to_vertical(
    input_path: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
) -> str | None:
    """
    Скропить видео в вертикальный формат 9:16.

    MVP: центральный кроп. Если исходник 16:9 — берём центральную
    вертикальную полосу. Если уже 9:16 — масштабируем без кропа.

    Args:
        input_path: Путь к исходному видеофайлу
        output_path: Путь к выходному файлу
        width: Ширина выходного видео (по умолчанию 1080)
        height: Высота выходного видео (по умолчанию 1920)

    Returns:
        Путь к выходному файлу или None при ошибке
    """
    logger.warning("crop_to_vertical() not implemented yet (stage 2)")
    return None


async def extract_segment(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
) -> str | None:
    """
    Вырезать сегмент из видео по временным меткам.

    Args:
        input_path: Путь к исходному видеофайлу
        output_path: Путь к выходному файлу
        start_time: Начало сегмента в секундах
        end_time: Конец сегмента в секундах

    Returns:
        Путь к выходному файлу или None при ошибке
    """
    logger.warning("extract_segment() not implemented yet (stage 2)")
    return None
