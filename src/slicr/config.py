import json
import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    """Ошибка загрузки конфигурации."""
    pass


@dataclass
class Config:
    # Telegram
    api_id: int = 0
    api_hash: str = ""
    bot_token: str = ""
    admin_id: int = 0
    tech_channel_id: int = 0
    target_channel_id: int = 0

    # Claude API
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_proxy_url: str = ""
    # URL прокси для Claude API (Cloudflare Worker)
    # Пример: "https://ai-proxy.nikneym24.workers.dev/claude"
    # Если пусто — прямое подключение к api.anthropic.com

    # Groq API
    groq_api_key: str = ""
    groq_proxy_url: str = ""

    # HTTP-прокси для внешних API (V2Ray, SOCKS и т.д.)
    # Пример: "http://127.0.0.1:10801"
    http_proxy: str = ""

    # VK
    vk_access_token: str = ""
    vk_group_id: int = 0

    # Pipeline
    min_video_duration: int = 30
    max_video_duration: int = 7200
    min_clip_duration: int = 15
    max_clip_duration: int = 60

    # Whisper
    whisper_model: str = "medium"
    whisper_compute_type: str = "int8"
    whisper_language: str = "ru"

    # GPU Guard
    gpu_guard_enabled: bool = True
    gpu_min_free_vram_gb: float = 3.0

    # Storage
    storage_base: str = "./storage"

    # Source channels
    source_channels: list[int] = field(default_factory=list)

    # Telegram каналы
    buffer_channel_id: int = 0
    # Канал-буфер: хранилище пересланных видео

    # Proxy
    proxy: dict | None = None
    # Формат: {"type": "socks5", "host": "...", "port": 1080, "username": "...", "password": "..."}
    # Или:    {"type": "mtproto", "host": "...", "port": ..., "secret": "..."}
    # Или None — прямое подключение

    # Session
    session_string: str = ""
    # StringSession для Telethon (альтернатива файловой сессии)

    # Download
    max_concurrent_downloads: int = 1
    max_file_size: int = 2 * 1024 * 1024 * 1024  # 2 GB

    # Cleanup
    cleanup_enabled: bool = True
    cleanup_after_hours: int = 48

    # Text filter
    filter_keywords: list[str] = field(default_factory=list)
    # Whitelist: если не пустой, caption должен содержать хотя бы одно слово
    filter_stopwords: list[str] = field(default_factory=list)
    # Blacklist: если caption содержит стоп-слово — пропускаем

    # Dev mode
    dev_mode: bool = False
    mock_gpu: bool = False
    mock_selector: bool = False
    mock_monitor: bool = False

    # DB
    db_path: str = "slicr.db"


def load_config(path: str = "creds.json") -> Config:
    """
    Загружает конфигурацию из JSON-файла с перезаписью через переменные окружения.

    Переменные окружения:
        SLICR_DEV=1       → dev_mode=True
        SLICR_MOCK_GPU=1  → mock_gpu=True
        SLICR_MOCK_SELECTOR=1 → mock_selector=True
        SLICR_MOCK_MONITOR=1  → mock_monitor=True

    Если файл не найден и dev_mode=True — работает с дефолтами.
    Если файл не найден и dev_mode=False — поднимает ConfigError.
    """
    # Сначала определяем dev_mode из env, чтобы понять как обрабатывать отсутствующий файл
    env_dev_mode = os.environ.get("SLICR_DEV", "").strip() == "1"

    data: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        if env_dev_mode or data.get("dev_mode", False):
            # Работаем с дефолтами в dev-режиме
            pass
        else:
            raise ConfigError(
                f"Файл конфигурации '{path}' не найден. "
                "Создайте его на основе creds.example.json или установите "
                "переменную окружения SLICR_DEV=1 для dev-режима."
            )
    except json.JSONDecodeError as e:
        raise ConfigError(f"Ошибка парсинга файла конфигурации '{path}': {e}")

    config = Config(
        api_id=int(data.get("api_id", 0)),
        api_hash=data.get("api_hash", ""),
        bot_token=data.get("bot_token", ""),
        admin_id=int(data.get("admin_id", 0)),
        tech_channel_id=int(data.get("tech_channel_id", 0)),
        target_channel_id=int(data.get("target_channel_id", 0)),
        claude_api_key=data.get("claude_api_key", ""),
        claude_model=data.get("claude_model", "claude-sonnet-4-20250514"),
        claude_proxy_url=data.get("claude_proxy_url", ""),
        groq_api_key=data.get("groq_api_key", ""),
        groq_proxy_url=data.get("groq_proxy_url", ""),
        http_proxy=data.get("http_proxy", ""),
        vk_access_token=data.get("vk_access_token", ""),
        vk_group_id=int(data.get("vk_group_id", 0)),
        min_video_duration=int(data.get("min_video_duration", 30)),
        max_video_duration=int(data.get("max_video_duration", 7200)),
        min_clip_duration=int(data.get("min_clip_duration", 15)),
        max_clip_duration=int(data.get("max_clip_duration", 60)),
        whisper_model=data.get("whisper_model", "medium"),
        whisper_compute_type=data.get("whisper_compute_type", "int8"),
        whisper_language=data.get("whisper_language", "ru"),
        gpu_guard_enabled=bool(data.get("gpu_guard_enabled", True)),
        gpu_min_free_vram_gb=float(data.get("gpu_min_free_vram_gb", 3.0)),
        storage_base=data.get("storage_base", "./storage"),
        source_channels=list(data.get("source_channels", [])),
        buffer_channel_id=int(data.get("buffer_channel_id", 0)),
        proxy=data.get("proxy", None),
        session_string=data.get("session_string", ""),
        max_concurrent_downloads=int(data.get("max_concurrent_downloads", 1)),
        max_file_size=int(data.get("max_file_size", 2 * 1024 * 1024 * 1024)),
        cleanup_enabled=bool(data.get("cleanup_enabled", True)),
        cleanup_after_hours=int(data.get("cleanup_after_hours", 48)),
        filter_keywords=list(data.get("filter_keywords", [])),
        filter_stopwords=list(data.get("filter_stopwords", [])),
        dev_mode=bool(data.get("dev_mode", False)),
        mock_gpu=bool(data.get("mock_gpu", False)),
        mock_selector=bool(data.get("mock_selector", False)),
        mock_monitor=bool(data.get("mock_monitor", False)),
        db_path=data.get("db_path", "slicr.db"),
    )

    # Переменные окружения перезаписывают JSON
    if env_dev_mode:
        config.dev_mode = True
    if os.environ.get("SLICR_MOCK_GPU", "").strip() == "1":
        config.mock_gpu = True
    if os.environ.get("SLICR_MOCK_SELECTOR", "").strip() == "1":
        config.mock_selector = True
    if os.environ.get("SLICR_MOCK_MONITOR", "").strip() == "1":
        config.mock_monitor = True

    return config
