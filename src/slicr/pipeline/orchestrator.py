"""
Оркестратор конвейера обработки видео.

Координирует весь pipeline: управляет очередями CPU/GPU/Moderation задач,
запускает воркеры, обрабатывает retry-логику.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Координатор конвейера обработки видео. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def start(self) -> None:
        """Запустить оркестратор и все воркеры."""
        logger.warning("PipelineOrchestrator.start() not implemented yet (stage 2)")

    async def stop(self) -> None:
        """Graceful shutdown: дождаться завершения текущих задач."""
        logger.warning("PipelineOrchestrator.stop() not implemented yet (stage 2)")

    async def process_video(self, video_id: int) -> None:
        """Запустить обработку видео через конвейер."""
        logger.warning("PipelineOrchestrator.process_video() not implemented yet (stage 2)")
