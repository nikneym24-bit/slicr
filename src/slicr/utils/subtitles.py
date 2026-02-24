"""
Генерация файлов субтитров.

Создаёт SRT и ASS субтитры из word-level транскрипции faster-whisper.
ASS поддерживает karaoke-эффект (подсветка слово за словом) для TikTok-стиля.

Реализация: этап 2.
"""

import logging

logger = logging.getLogger(__name__)


def generate_srt(words: list[dict], output_path: str) -> str | None:
    """
    Сгенерировать SRT-субтитры из word-level транскрипции.

    Args:
        words: Список слов с полями: word, start, end, probability
        output_path: Путь к выходному .srt файлу

    Returns:
        Путь к файлу субтитров или None при ошибке
    """
    logger.warning("generate_srt() not implemented yet (stage 2)")
    return None


def generate_ass(words: list[dict], output_path: str) -> str | None:
    """
    Сгенерировать ASS-субтитры с karaoke-эффектом из word-level транскрипции.

    Args:
        words: Список слов с полями: word, start, end, probability
        output_path: Путь к выходному .ass файлу

    Returns:
        Путь к файлу субтитров или None при ошибке
    """
    logger.warning("generate_ass() not implemented yet (stage 2)")
    return None
