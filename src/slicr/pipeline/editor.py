"""
Видеоредактор — монтаж клипа.

Вырезает фрагмент, кропает в формат 9:16 (1080x1920),
накладывает субтитры. Кодирование CPU-only (libx264), без NVENC.

Реализация: этап 2.
"""

import logging
from slicr.config import Config
from slicr.database import Database

logger = logging.getLogger(__name__)


class VideoEditor:
    """Монтаж клипа через ffmpeg. Заглушка для этапа 2."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def create_clip(self, clip_id: int) -> str | None:
        """
        Смонтировать финальный клип: вырезка + кроп 9:16 + субтитры.
        Возвращает путь к готовому файлу или None при ошибке.
        """
        logger.warning("VideoEditor.create_clip() not implemented yet (stage 2)")
        return None
