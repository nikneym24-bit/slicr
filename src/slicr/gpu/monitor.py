"""
GPU Watchdog — мониторинг GPU во время выполнения задач.

Отслеживает состояние GPU каждые 2 секунды пока работает whisper.
При падении свободной VRAM ниже порога — прерывает задачу.
В mock-режиме ничего не делает.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class GPUWatchdog:
    """
    Runtime-мониторинг GPU. Заглушка для этапа 2.

    В продакшене использует pynvml, опрашивает VRAM каждые 2 сек.
    На macOS работает в mock-режиме (SLICR_MOCK_GPU=1).
    """

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def start_watching(self) -> None:
        """Начать мониторинг GPU в фоне."""
        logger.warning("GPUWatchdog.start_watching() not implemented yet (stage 2)")

    async def stop_watching(self) -> None:
        """Остановить мониторинг GPU."""
        logger.warning("GPUWatchdog.stop_watching() not implemented yet (stage 2)")
