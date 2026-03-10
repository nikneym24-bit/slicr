"""
Утилиты для работы с видео через ffmpeg.

Хелперы для нарезки фрагментов и кропа в вертикальный формат 9:16.
Все операции — CPU-only (libx264), без NVENC/CUDA.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def extract_segment(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
) -> str | None:
    """
    Вырезать сегмент из видео по временным меткам.

    Использует перекодировку (libx264) для точной нарезки без артефактов
    на стыках ключевых кадров.

    Returns:
        Путь к выходному файлу или None при ошибке.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", input_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]

    logger.debug(f"ffmpeg extract: {' '.join(cmd)}")
    logger.info(
        f"Вырезаем сегмент [{start_time:.1f}-{end_time:.1f}] "
        f"из {input_path}"
    )

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode(errors="replace")[-500:]
        logger.error(f"ffmpeg extract_segment ошибка: {error}")
        return None

    logger.info(f"Сегмент вырезан: {output_path}")
    return output_path


async def crop_to_vertical(
    input_path: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    crop_x_offset: float = 0.5,
) -> str | None:
    """
    Скропить видео в вертикальный формат 9:16.

    Args:
        crop_x_offset: горизонтальное смещение кропа (0.0 = лево, 0.5 = центр, 1.0 = право).

    Returns:
        Путь к выходному файлу или None при ошибке.
    """
    # crop_width = ih*9/16, crop_x = (iw - crop_width) * offset
    offset = max(0.0, min(1.0, crop_x_offset))
    vf = (
        f"crop=trunc(ih*9/16/2)*2:trunc(ih/2)*2:"
        f"trunc((iw-ih*9/16)*{offset:.4f}/2)*2:0,"
        f"scale={width}:{height}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]

    logger.debug(f"ffmpeg crop: {' '.join(cmd)}")
    logger.info(f"Кроп в {width}x{height}: {input_path}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode(errors="replace")[-500:]
        logger.error(f"ffmpeg crop_to_vertical ошибка: {error}")
        return None

    logger.info(f"Кроп завершён: {output_path}")
    return output_path


async def burn_subtitles(
    input_path: str,
    subtitle_path: str,
    output_path: str,
) -> str | None:
    """
    Наложить ASS-субтитры на видео (hardcode/burn-in).

    Returns:
        Путь к выходному файлу или None при ошибке.
    """
    # Экранируем путь к субтитрам для ffmpeg filter (: и \ нужно экранировать)
    escaped_sub = subtitle_path.replace("\\", "\\\\").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"ass={escaped_sub}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]

    logger.debug(f"ffmpeg subtitles: {' '.join(cmd)}")
    logger.info(f"Накладываем субтитры: {subtitle_path}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode(errors="replace")[-500:]
        logger.error(f"ffmpeg burn_subtitles ошибка: {error}")
        return None

    logger.info(f"Субтитры наложены: {output_path}")
    return output_path
