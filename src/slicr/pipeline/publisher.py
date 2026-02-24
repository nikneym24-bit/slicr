"""
Публикатор клипов.

Публикует одобренные клипы в VK Clips и/или Telegram-канал.
Обновляет статус клипа и создаёт записи в таблице publications.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class ClipPublisher:
    """Публикация клипов в VK и Telegram. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def publish_vk(self, clip_id: int) -> str | None:
        """
        Опубликовать клип в VK Clips.
        Возвращает ID поста на VK или None при ошибке.
        """
        logger.warning("ClipPublisher.publish_vk() not implemented yet (stage 2)")
        return None

    async def publish_telegram(self, clip_id: int) -> str | None:
        """
        Опубликовать клип в Telegram-канал.
        Возвращает ID сообщения или None при ошибке.
        """
        logger.warning("ClipPublisher.publish_telegram() not implemented yet (stage 2)")
        return None
