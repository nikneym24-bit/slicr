import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from video_clipper.database.models import Database

logger = logging.getLogger(__name__)

CURRENT_VERSION = 2


async def run_migrations(db: "Database") -> None:
    """
    Выполняет автомиграции базы данных.
    Версия схемы хранится в таблице settings по ключу 'schema_version'.
    Версия 1 — начальная схема (init_tables).
    Версия 2 — добавление buffer_message_id в таблицу videos.
    """
    version_str = await db.get_setting("schema_version", "0")
    version = int(version_str)
    logger.info(f"Текущая версия схемы: {version}, целевая: {CURRENT_VERSION}")

    if version < 1:
        logger.info("Применяется миграция v1: начальная схема")
        await db.init_tables()
        await db.set_setting("schema_version", "1")
        logger.info("Миграция v1 применена")

    if version < 2:
        logger.info("Применяется миграция v2: добавление buffer_message_id")
        await migrate_add_buffer_message_id(db)
        await db.set_setting("schema_version", "2")
        logger.info("Миграция v2 применена")

    if version == CURRENT_VERSION:
        logger.debug("Схема БД актуальна")


async def migrate_add_buffer_message_id(db: "Database") -> None:
    """Добавить buffer_message_id в таблицу videos."""
    async with db._get_connection() as conn:
        try:
            await conn.execute("ALTER TABLE videos ADD COLUMN buffer_message_id INTEGER")
        except Exception:
            pass  # Колонка уже существует
