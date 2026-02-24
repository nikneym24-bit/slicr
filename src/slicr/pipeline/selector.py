"""
AI-отбор лучшего момента из транскрипции.

Использует Claude API для анализа транскрипции и выбора самого
вирального фрагмента длительностью 15–60 секунд.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class MomentSelector:
    """AI-отбор момента через Claude API. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def select_moment(self, video_id: int, transcription_id: int) -> int | None:
        """
        Выбрать лучший фрагмент из транскрипции.
        Возвращает clip_id или None если подходящий момент не найден.
        """
        logger.warning("MomentSelector.select_moment() not implemented yet (stage 2)")
        return None
