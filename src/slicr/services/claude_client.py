"""
Клиент Claude API для AI-отбора моментов.

Отправляет транскрипцию в Claude API и получает структурированный JSON
с выбранным фрагментом: start_time, end_time, title, reason, score.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Клиент Claude API. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def analyze_transcript(
        self,
        transcript: str,
        duration: float,
    ) -> dict | None:
        """
        Анализировать транскрипцию и выбрать лучший фрагмент.

        Args:
            transcript: Текст транскрипции с таймкодами
            duration: Полная длительность видео в секундах

        Returns:
            Словарь с полями: start_time, end_time, title, description,
            reason, score, keywords — или None если момент не найден
        """
        logger.warning("ClaudeClient.analyze_transcript() not implemented yet (stage 2)")
        return None
