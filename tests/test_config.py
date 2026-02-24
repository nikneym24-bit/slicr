import json
import os
import pytest
from slicr.config import load_config, Config, ConfigError


def test_load_config_from_file(tmp_path):
    """Создать tmp creds.json, загрузить, проверить поля."""
    creds = {
        "api_id": 12345,
        "api_hash": "test_hash",
        "bot_token": "test_token",
        "admin_id": 99999,
        "tech_channel_id": -100111,
        "target_channel_id": -100222,
        "claude_api_key": "sk-ant-test",
        "claude_model": "claude-sonnet-4-20250514",
        "vk_access_token": "vk_token",
        "vk_group_id": 42,
        "source_channels": [111, 222],
        "dev_mode": False,
        "mock_gpu": False,
        "mock_selector": False,
        "mock_monitor": False,
    }
    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps(creds))

    config = load_config(str(creds_file))

    assert config.api_id == 12345
    assert config.api_hash == "test_hash"
    assert config.bot_token == "test_token"
    assert config.admin_id == 99999
    assert config.claude_api_key == "sk-ant-test"
    assert config.vk_group_id == 42
    assert config.source_channels == [111, 222]
    assert config.dev_mode is False


def test_dev_mode_from_env(tmp_path, monkeypatch):
    """Установить env SLICR_DEV=1, проверить config.dev_mode == True."""
    monkeypatch.setenv("SLICR_DEV", "1")

    # Без файла должно работать в dev-режиме
    config = load_config(str(tmp_path / "nonexistent_creds.json"))
    assert config.dev_mode is True


def test_missing_creds_raises(tmp_path, monkeypatch):
    """Без файла и без dev_mode → ConfigError."""
    monkeypatch.delenv("SLICR_DEV", raising=False)
    monkeypatch.delenv("SLICR_MOCK_GPU", raising=False)

    with pytest.raises(ConfigError):
        load_config(str(tmp_path / "nonexistent_creds.json"))
