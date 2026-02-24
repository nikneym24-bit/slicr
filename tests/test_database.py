import pytest
from slicr.database import Database


@pytest.mark.asyncio
async def test_init_tables(db: Database):
    """БД создаётся, все 7 таблиц существуют."""
    async with db._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        tables = {row["name"] for row in rows}

    expected = {"videos", "transcriptions", "clips", "jobs", "publications", "sources", "settings"}
    # sqlite_sequence — внутренняя таблица SQLite (создаётся при AUTOINCREMENT), исключаем
    user_tables = {t for t in tables if not t.startswith("sqlite_")}
    assert expected == user_tables, f"Таблицы не совпадают: {user_tables}"


@pytest.mark.asyncio
async def test_add_video(db: Database):
    """Добавить видео, получить по id, проверить поля."""
    video_id = await db.add_video(
        source_chat_id=100,
        source_message_id=200,
        duration=120.5,
        caption="Test caption",
        file_size=1024,
        width=1280,
        height=720,
    )
    assert video_id is not None
    assert video_id > 0

    video = await db.get_video(video_id)
    assert video is not None
    assert video["source_chat_id"] == 100
    assert video["source_message_id"] == 200
    assert video["duration"] == 120.5
    assert video["caption"] == "Test caption"
    assert video["file_size"] == 1024
    assert video["width"] == 1280
    assert video["height"] == 720
    assert video["status"] == "queued"


@pytest.mark.asyncio
async def test_duplicate_video(db: Database):
    """Добавить дубль → is_duplicate возвращает True."""
    await db.add_video(source_chat_id=100, source_message_id=200)

    result = await db.is_duplicate(source_chat_id=100, source_message_id=200)
    assert result is True

    result_no_dup = await db.is_duplicate(source_chat_id=100, source_message_id=999)
    assert result_no_dup is False


@pytest.mark.asyncio
async def test_video_status_update(db: Database):
    """Обновить статус видео, проверить."""
    video_id = await db.add_video(source_chat_id=1, source_message_id=1)

    await db.update_video_status(video_id, "downloading")
    video = await db.get_video(video_id)
    assert video["status"] == "downloading"

    await db.update_video_status(video_id, "failed", error_message="Network error")
    video = await db.get_video(video_id)
    assert video["status"] == "failed"
    assert video["error_message"] == "Network error"


@pytest.mark.asyncio
async def test_add_job_and_get_next(db: Database):
    """Создать задачу, get_next_job возвращает её, статус стал running."""
    video_id = await db.add_video(source_chat_id=1, source_message_id=1)
    job_id = await db.add_job(job_type="download", video_id=video_id)
    assert job_id is not None
    assert job_id > 0

    job = await db.get_next_job()
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == "running"
    assert job["job_type"] == "download"
    assert job["video_id"] == video_id


@pytest.mark.asyncio
async def test_get_next_job_empty(db: Database):
    """Пустая очередь → None."""
    job = await db.get_next_job()
    assert job is None


@pytest.mark.asyncio
async def test_settings(db: Database):
    """set_setting / get_setting работают корректно."""
    await db.set_setting("test_key", "test_value")
    value = await db.get_setting("test_key")
    assert value == "test_value"

    # Перезапись
    await db.set_setting("test_key", "new_value")
    value = await db.get_setting("test_key")
    assert value == "new_value"

    # Несуществующий ключ
    missing = await db.get_setting("nonexistent", default="fallback")
    assert missing == "fallback"


@pytest.mark.asyncio
async def test_sources(db: Database):
    """add_source / get_active_sources работают корректно."""
    await db.add_source(chat_id=12345, chat_title="Test Channel", chat_username="testchannel")
    await db.add_source(chat_id=67890, chat_title="Another Channel")

    sources = await db.get_active_sources()
    assert len(sources) == 2

    chat_ids = {s["chat_id"] for s in sources}
    assert 12345 in chat_ids
    assert 67890 in chat_ids

    # Повторное добавление не создаёт дубль (INSERT OR IGNORE)
    await db.add_source(chat_id=12345, chat_title="Duplicate")
    sources = await db.get_active_sources()
    assert len(sources) == 2
