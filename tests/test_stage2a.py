"""Тесты для Stage 2a: TelegramClientWrapper + TelegramMonitor."""

import pytest
import pytest_asyncio

from slicr.config import Config
from slicr.database import Database
from slicr.constants import VideoStatus


# ─────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────

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
        tech_channel_id=-1009999999999,
        target_channel_id=0,
        buffer_channel_id=-1008888888888,
        claude_api_key="test",
        vk_access_token="test",
        vk_group_id=0,
        source_channels=[-1001234567890],
        storage_base=str(tmp_path / "storage"),
        min_video_duration=30,
        max_video_duration=7200,
        max_file_size=2 * 1024 * 1024 * 1024,
        max_concurrent_downloads=1,
        cleanup_enabled=True,
        cleanup_after_hours=48,
        proxy=None,
        session_string="",
        filter_keywords=[],
        filter_stopwords=[],
    )


# ─────────────────────────────────────────────────────
# TelegramClientWrapper
# ─────────────────────────────────────────────────────

class TestTelegramClientWrapper:

    def test_init_no_proxy(self, config):
        """Создание клиента без прокси."""
        from slicr.services.telegram_client import TelegramClientWrapper
        wrapper = TelegramClientWrapper(config)
        assert wrapper is not None
        assert wrapper.client is not None

    def test_init_session_string(self, config):
        """Создание клиента с session_string (мокируем StringSession — Telethon валидирует формат)."""
        from unittest.mock import patch, MagicMock
        config.session_string = "some_session_string"
        with patch("telethon.sessions.StringSession") as mock_ss:
            mock_ss.return_value = MagicMock()
            from slicr.services.telegram_client import TelegramClientWrapper
            with patch("telethon.TelegramClient"):
                wrapper = TelegramClientWrapper(config)
                assert wrapper is not None
                mock_ss.assert_called_once_with("some_session_string")

    def test_init_socks5_proxy(self, config):
        """Создание клиента с SOCKS5 прокси."""
        config.proxy = {"type": "socks5", "host": "127.0.0.1", "port": 1080}
        from slicr.services.telegram_client import TelegramClientWrapper
        wrapper = TelegramClientWrapper(config)
        assert wrapper is not None

    def test_extract_video_info_none(self, config):
        """extract_video_info возвращает None для не-видео."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.video = None
        assert TelegramClientWrapper.extract_video_info(msg) is None

    def test_extract_video_info_with_video(self, config):
        """extract_video_info возвращает dict для видео."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from unittest.mock import MagicMock
        from telethon.tl.types import DocumentAttributeVideo

        attr = MagicMock(spec=DocumentAttributeVideo)
        attr.duration = 120
        attr.w = 1280
        attr.h = 720

        video = MagicMock()
        video.attributes = [attr]
        video.size = 50 * 1024 * 1024  # 50 MB

        msg = MagicMock()
        msg.video = video

        info = TelegramClientWrapper.extract_video_info(msg)
        assert info is not None
        assert info["duration"] == 120
        assert info["width"] == 1280
        assert info["height"] == 720
        assert info["file_size"] == 50 * 1024 * 1024


# ─────────────────────────────────────────────────────
# TelegramMonitor
# ─────────────────────────────────────────────────────

class TestTelegramMonitor:

    def test_init(self, config, db):
        """Инициализация монитора."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_mock_start(self, config, db):
        """Mock-режим: start() не подключается к Telegram."""
        config.mock_monitor = True
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        await monitor.start()
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_sync_sources(self, config, db):
        """Синхронизация source_channels из конфига в БД."""
        config.source_channels = [-1001111111111, -1002222222222]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        await monitor._sync_sources()
        sources = await db.get_active_sources()
        chat_ids = [s["chat_id"] for s in sources]
        assert -1001111111111 in chat_ids
        assert -1002222222222 in chat_ids

    def test_text_filter_no_filter(self, config, db):
        """Без фильтров — пропускает всё."""
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter(None) is True
        assert monitor._check_text_filter("любой текст") is True
        assert monitor._check_text_filter("") is True

    def test_text_filter_keywords(self, config, db):
        """Whitelist: пропускает только посты с ключевыми словами."""
        config.filter_keywords = ["подкаст", "интервью"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Новый подкаст с гостем") is True
        assert monitor._check_text_filter("Интервью дня") is True
        assert monitor._check_text_filter("Просто видео") is False
        assert monitor._check_text_filter(None) is False  # нет текста — не проходит whitelist

    def test_text_filter_stopwords(self, config, db):
        """Blacklist: блокирует посты со стоп-словами."""
        config.filter_stopwords = ["реклама", "#ad"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Отличное видео") is True
        assert monitor._check_text_filter("Реклама партнёра") is False
        assert monitor._check_text_filter("Пост с #ad тегом") is False

    def test_text_filter_both(self, config, db):
        """Whitelist + Blacklist одновременно."""
        config.filter_keywords = ["подкаст"]
        config.filter_stopwords = ["реклама"]
        from slicr.services.telegram_client import TelegramClientWrapper
        from slicr.pipeline.monitor import TelegramMonitor
        tg = TelegramClientWrapper(config)
        monitor = TelegramMonitor(config, db, tg)
        assert monitor._check_text_filter("Подкаст #42") is True
        assert monitor._check_text_filter("Подкаст — реклама") is False  # стоп-слово
        assert monitor._check_text_filter("Видео дня") is False  # нет ключевого


# ─────────────────────────────────────────────────────
# Config — новые поля
# ─────────────────────────────────────────────────────

class TestConfigNewFields:

    def test_defaults(self):
        c = Config()
        assert c.proxy is None
        assert c.session_string == ""
        assert c.buffer_channel_id == 0
        assert c.max_concurrent_downloads == 1
        assert c.max_file_size == 2 * 1024 * 1024 * 1024
        assert c.cleanup_enabled is True
        assert c.cleanup_after_hours == 48
        assert c.filter_keywords == []
        assert c.filter_stopwords == []

    def test_load_proxy(self, tmp_path):
        """Загрузка прокси из JSON."""
        import json
        from slicr.config import load_config
        creds = {"dev_mode": True, "proxy": {"type": "socks5", "host": "1.2.3.4", "port": 1080}}
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.proxy["type"] == "socks5"

    def test_load_session_string(self, tmp_path):
        """Загрузка session_string из JSON."""
        import json
        from slicr.config import load_config
        creds = {"dev_mode": True, "session_string": "abc123"}
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.session_string == "abc123"

    def test_load_filter_keywords(self, tmp_path):
        """Загрузка keywords/stopwords из JSON."""
        import json
        from slicr.config import load_config
        creds = {
            "dev_mode": True,
            "filter_keywords": ["подкаст"],
            "filter_stopwords": ["реклама"],
        }
        path = tmp_path / "creds.json"
        path.write_text(json.dumps(creds))
        config = load_config(str(path))
        assert config.filter_keywords == ["подкаст"]
        assert config.filter_stopwords == ["реклама"]
