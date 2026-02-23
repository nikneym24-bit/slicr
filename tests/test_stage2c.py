"""Тесты для Stage 2c: VideoDownloader."""

import pytest
import pytest_asyncio
from pathlib import Path

from video_clipper.config import Config
from video_clipper.database import Database
from video_clipper.constants import VideoStatus, JobType, JobStatus


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init_tables()
    yield database
    await database.close()


@pytest.fixture
def config(tmp_path):
    return Config(
        dev_mode=True,
        mock_gpu=True,
        mock_selector=True,
        mock_monitor=True,
        db_path=":memory:",
        api_id=12345,
        api_hash="test_hash",
        bot_token="test_token",
        admin_id=0,
        tech_channel_id=0,
        target_channel_id=0,
        buffer_channel_id=-1008888888888,
        claude_api_key="test",
        vk_access_token="test",
        vk_group_id=0,
        source_channels=[],
        storage_base=str(tmp_path / "storage"),
        max_concurrent_downloads=1,
        max_file_size=2 * 1024 * 1024 * 1024,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        proxy=None,
        session_string="",
        filter_keywords=[],
        filter_stopwords=[],
    )


class TestVideoDownloader:

    def test_init(self, config, db):
        """Инициализация загрузчика."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        assert dl._running is False

    async def test_download_nonexistent(self, config, db):
        """Скачивание несуществующего видео → None."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        result = await dl.download(9999)
        assert result is None

    async def test_mock_download(self, config, db):
        """Mock-режим: создаёт пустой файл."""
        config.mock_monitor = True
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)

        video_id = await db.add_video(
            source_chat_id=-1001234567890,
            source_message_id=100,
            duration=60.0,
            file_size=1024 * 1024,
        )

        result = await dl.download(video_id)
        assert result is not None
        assert Path(result).exists()
        assert result.endswith(".mp4")

        video = await db.get_video(video_id)
        assert video["status"] == VideoStatus.DOWNLOADED
        assert video["file_path"] == result

    async def test_mock_download_creates_directory(self, config, db):
        """Mock: создаёт директорию downloads/ если не существует."""
        config.mock_monitor = True
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)

        video_id = await db.add_video(-100, 1, duration=60)
        result = await dl.download(video_id)

        downloads_dir = Path(config.storage_base) / "downloads"
        assert downloads_dir.exists()

    async def test_cleanup_no_files(self, config, db):
        """Очистка при пустой БД."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        await dl.cleanup_old_files()  # не должен упасть

    async def test_cleanup_disabled(self, config, db):
        """Очистка отключена в конфиге."""
        config.cleanup_enabled = False
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        await dl.cleanup_old_files()  # не должен упасть

    def test_progress_callback(self, config, db):
        """Прогресс-callback не падает."""
        from video_clipper.services.telegram_client import TelegramClientWrapper
        from video_clipper.pipeline.downloader import VideoDownloader
        tg = TelegramClientWrapper(config)
        dl = VideoDownloader(config, db, tg)
        cb = dl._make_progress_callback(1)
        cb(0, 100)
        cb(50, 100)
        cb(100, 100)
        cb(0, 0)  # edge case


class TestDatabaseCleanupMethods:

    async def test_get_videos_for_cleanup_empty(self, db):
        """Пустая БД — нет видео для очистки."""
        videos = await db.get_videos_for_cleanup(48)
        assert videos == []

    async def test_clear_video_file(self, db):
        """Очистка пути к файлу."""
        video_id = await db.add_video(-100, 1, duration=60)
        await db.update_video_file(video_id, "/tmp/test.mp4", 1024)

        video = await db.get_video(video_id)
        assert video["file_path"] == "/tmp/test.mp4"

        await db.clear_video_file(video_id)
        video = await db.get_video(video_id)
        assert video["file_path"] is None

    async def test_update_video_buffer_message(self, db):
        """Сохранение buffer_message_id."""
        video_id = await db.add_video(-100, 1, duration=60)
        await db.update_video_buffer_message(video_id, 12345)
        video = await db.get_video(video_id)
        assert video["buffer_message_id"] == 12345
