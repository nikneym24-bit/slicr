"""
GPU Guard — защита GPU от конфликтов с оператором.

Выполняет pre-flight проверку перед каждой GPU-задачей:
свободная VRAM, GPU-процессы, утилизация.
В mock-режиме (macOS без NVIDIA GPU) всегда разрешает выполнение.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class GPUGuard:
    """
    Защита GPU от конфликтов. Заглушка для этапа 2.

    В продакшене использует pynvml для проверки VRAM и GPU-процессов.
    На macOS работает в mock-режиме (SLICR_MOCK_GPU=1).
    """

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def check_available(self) -> bool:
        """
        Проверить доступность GPU для выполнения задачи.
        Возвращает True если GPU свободен, False если занят оператором.
        """
        logger.warning("GPUGuard.check_available() not implemented yet (stage 2)")
        return True  # В mock-режиме всегда доступен

    async def acquire(self) -> bool:
        """
        Захватить GPU для выполнения задачи.
        Возвращает True если захват успешен.
        """
        logger.warning("GPUGuard.acquire() not implemented yet (stage 2)")
        return True

    async def release(self) -> None:
        """Освободить GPU после завершения задачи."""
        logger.warning("GPUGuard.release() not implemented yet (stage 2)")
