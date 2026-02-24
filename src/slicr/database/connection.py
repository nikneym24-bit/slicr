import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)


class ConnectionMixin:
    """
    Миксин для работы с долгоживущим aiosqlite-соединением.
    Кэширует одно соединение, настраивает PRAGMA, управляет транзакциями.
    """

    db_path: str
    _conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        Возвращает кэшированное соединение с базой данных.
        Применяет PRAGMA при первом подключении.
        При успехе — commit, при ошибке — rollback.
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON")
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute("PRAGMA busy_timeout = 5000")
            logger.debug(f"Database connection opened: {self.db_path}")

        try:
            yield self._conn
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def close(self) -> None:
        """Закрыть соединение с базой данных."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")
