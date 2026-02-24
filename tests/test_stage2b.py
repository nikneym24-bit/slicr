"""Тесты для Stage 2b: Bot + Модерация + Команды."""

import pytest
import pytest_asyncio

from slicr.config import Config
from slicr.database import Database
from slicr.constants import VideoStatus, JobType


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init_tables()
    yield database
    await database.close()


# ─────────────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────────────

class TestKeyboards:

    def test_moderation_keyboard(self):
        """Клавиатура модерации содержит Approve и Reject."""
        from slicr.bot.keyboards import get_moderation_keyboard
        kb = get_moderation_keyboard(42)
        buttons = kb.inline_keyboard[0]
        assert len(buttons) == 2
        assert buttons[0].callback_data == "approve:42"
        assert buttons[1].callback_data == "reject:42"

    def test_format_video_info(self):
        """Форматирование инфо о видео."""
        from slicr.bot.keyboards import format_video_info
        video = {
            "id": 1,
            "source_chat_id": -1001234567890,
            "duration": 120,
            "file_size": 50 * 1024 * 1024,
        }
        text = format_video_info(video)
        assert "120" in text
        assert "#1" in text

    def test_format_video_info_no_size(self):
        """Форматирование без размера файла."""
        from slicr.bot.keyboards import format_video_info
        video = {"id": 2, "source_chat_id": -100, "duration": 60, "file_size": 0}
        text = format_video_info(video)
        assert "60" in text


# ─────────────────────────────────────────────────────
# Database — новые методы
# ─────────────────────────────────────────────────────

class TestDatabaseNewMethods:

    async def test_remove_source(self, db):
        """Удаление источника."""
        await db.add_source(-1001111111111, "Test Channel")
        result = await db.remove_source(-1001111111111)
        assert result is True
        sources = await db.get_active_sources()
        assert len(sources) == 0

    async def test_remove_source_nonexistent(self, db):
        """Удаление несуществующего источника."""
        result = await db.remove_source(-9999)
        assert result is False

    async def test_increment_video_count(self, db):
        """Инкремент счётчика видео."""
        await db.add_source(-1001111111111, "Test")
        await db.increment_video_count(-1001111111111)
        await db.increment_video_count(-1001111111111)
        sources = await db.get_active_sources()
        assert sources[0]["video_count"] == 2

    async def test_get_video_counts_by_status(self, db):
        """Подсчёт видео по статусам."""
        await db.add_video(-100, 1, duration=60)
        await db.add_video(-100, 2, duration=120)
        video_id = await db.add_video(-100, 3, duration=90)
        await db.update_video_status(video_id, VideoStatus.DOWNLOADED)

        counts = await db.get_video_counts_by_status()
        assert counts.get("queued", 0) == 2
        assert counts.get("downloaded", 0) == 1

    async def test_get_pending_jobs_count(self, db):
        """Количество задач в очереди."""
        count = await db.get_pending_jobs_count()
        assert count == 0

        # Создаём видео перед job-ами (FK constraint)
        vid1 = await db.add_video(-100, 1, duration=60)
        vid2 = await db.add_video(-100, 2, duration=120)
        await db.add_job(job_type=JobType.DOWNLOAD, video_id=vid1)
        await db.add_job(job_type=JobType.DOWNLOAD, video_id=vid2)
        count = await db.get_pending_jobs_count()
        assert count == 2


# ─────────────────────────────────────────────────────
# Handlers — _parse_telegram_link
# ─────────────────────────────────────────────────────

class TestParseTelegramLink:

    def test_https_link(self):
        from slicr.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("https://t.me/channel_name") == "channel_name"

    def test_at_username(self):
        from slicr.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("@channel_name") == "channel_name"

    def test_plain_username(self):
        from slicr.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("channel_name") == "channel_name"

    def test_invalid(self):
        from slicr.bot.handlers import _parse_telegram_link
        assert _parse_telegram_link("123") is None
        assert _parse_telegram_link("") is None
