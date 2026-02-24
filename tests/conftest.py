import pytest
import pytest_asyncio
from slicr.database import Database
from slicr.config import Config


@pytest_asyncio.fixture
async def db(tmp_path):
    """Фикстура: временная in-memory БД с инициализированными таблицами."""
    database = Database(str(tmp_path / "test.db"))
    await database.init_tables()
    yield database
    await database.close()


@pytest.fixture
def config():
    """Фикстура: конфигурация в dev-режиме со всеми mock-флагами."""
    return Config(
        dev_mode=True,
        mock_gpu=True,
        mock_selector=True,
        mock_monitor=True,
        db_path=":memory:",
        api_id=0,
        api_hash="test",
        bot_token="test",
        admin_id=0,
        tech_channel_id=0,
        target_channel_id=0,
        claude_api_key="test",
        vk_access_token="test",
        vk_group_id=0,
        buffer_channel_id=0,
        proxy=None,
        session_string="",
        max_concurrent_downloads=1,
        max_file_size=2 * 1024 * 1024 * 1024,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        filter_keywords=[],
        filter_stopwords=[],
    )
