"""
Транскрибатор речи на основе faster-whisper.

Выполняет STT с word-level таймкодами на GPU (RTX 4060 Ti, int8).
В dev-режиме на Mac работает на CPU (медленнее в ~10 раз).
Динамически загружает/выгружает модель из VRAM после каждой задачи.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Транскрибация через faster-whisper. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def transcribe(self, video_id: int) -> int | None:
        """
        Транскрибировать аудио из видео.
        Возвращает transcription_id или None при ошибке.
        """
        logger.warning("WhisperTranscriber.transcribe() not implemented yet (stage 2)")
        return None
