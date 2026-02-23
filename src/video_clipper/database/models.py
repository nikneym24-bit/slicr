import logging
from typing import Any

from video_clipper.database.connection import ConnectionMixin

logger = logging.getLogger(__name__)


class Database(ConnectionMixin):
    """
    Основной класс базы данных.
    Содержит методы инициализации таблиц и CRUD для всех сущностей.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = None

    # ------------------------------------------------------------------
    # Инициализация схемы
    # ------------------------------------------------------------------

    async def init_tables(self) -> None:
        """Создаёт все 7 таблиц базы данных если они не существуют."""
        async with self._get_connection() as conn:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_chat_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    buffer_message_id INTEGER,
                    file_path TEXT,
                    file_size INTEGER,
                    duration REAL,
                    width INTEGER,
                    height INTEGER,
                    caption TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_chat_id, source_message_id)
                );

                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES videos(id),
                    full_text TEXT NOT NULL,
                    language TEXT,
                    segments_json TEXT,
                    words_json TEXT,
                    model_name TEXT,
                    processing_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES videos(id),
                    transcription_id INTEGER REFERENCES transcriptions(id),
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    duration REAL NOT NULL,
                    title TEXT,
                    description TEXT,
                    ai_reason TEXT,
                    ai_score REAL,
                    transcript_fragment TEXT,
                    raw_clip_path TEXT,
                    final_clip_path TEXT,
                    subtitle_path TEXT,
                    status TEXT NOT NULL DEFAULT 'selected',
                    moderation_message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    moderated_at TIMESTAMP,
                    published_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER REFERENCES videos(id),
                    clip_id INTEGER REFERENCES clips(id),
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER DEFAULT 0,
                    requires_gpu BOOLEAN DEFAULT FALSE,
                    error_message TEXT,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clip_id INTEGER NOT NULL REFERENCES clips(id),
                    platform TEXT NOT NULL,
                    platform_post_id TEXT,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    reposts INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE NOT NULL,
                    chat_title TEXT,
                    chat_username TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    video_count INTEGER DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("Database tables initialized")

    # ------------------------------------------------------------------
    # Videos
    # ------------------------------------------------------------------

    async def add_video(
        self,
        source_chat_id: int,
        source_message_id: int,
        duration: float | None = None,
        caption: str | None = None,
        file_size: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> int:
        """Добавляет новое видео в базу, возвращает video_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO videos
                    (source_chat_id, source_message_id, duration, caption, file_size, width, height)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source_chat_id, source_message_id, duration, caption, file_size, width, height),
            )
            return cursor.lastrowid

    async def get_video(self, video_id: int) -> dict | None:
        """Возвращает видео по id или None если не найдено."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM videos WHERE id = ?", (video_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_video_status(
        self,
        video_id: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Обновляет статус видео."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                UPDATE videos
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error_message, video_id),
            )

    async def update_video_file(
        self,
        video_id: int,
        file_path: str,
        file_size: int | None = None,
    ) -> None:
        """Обновляет путь к файлу видео."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                UPDATE videos
                SET file_path = ?, file_size = COALESCE(?, file_size), updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (file_path, file_size, video_id),
            )

    async def is_duplicate(self, source_chat_id: int, source_message_id: int) -> bool:
        """Проверяет, существует ли видео с таким source_chat_id + source_message_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM videos WHERE source_chat_id = ? AND source_message_id = ?",
                (source_chat_id, source_message_id),
            )
            return await cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Transcriptions
    # ------------------------------------------------------------------

    async def add_transcription(
        self,
        video_id: int,
        full_text: str,
        segments_json: str | None = None,
        words_json: str | None = None,
        language: str | None = None,
        model_name: str | None = None,
        processing_time: float | None = None,
    ) -> int:
        """Добавляет транскрипцию, возвращает transcription_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO transcriptions
                    (video_id, full_text, segments_json, words_json, language, model_name, processing_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, full_text, segments_json, words_json, language, model_name, processing_time),
            )
            return cursor.lastrowid

    # ------------------------------------------------------------------
    # Clips
    # ------------------------------------------------------------------

    async def add_clip(
        self,
        video_id: int,
        transcription_id: int,
        start_time: float,
        end_time: float,
        duration: float,
        title: str | None = None,
        description: str | None = None,
        ai_reason: str | None = None,
        ai_score: float | None = None,
        transcript_fragment: str | None = None,
    ) -> int:
        """Добавляет клип, возвращает clip_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO clips
                    (video_id, transcription_id, start_time, end_time, duration,
                     title, description, ai_reason, ai_score, transcript_fragment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, transcription_id, start_time, end_time, duration,
                 title, description, ai_reason, ai_score, transcript_fragment),
            )
            return cursor.lastrowid

    async def update_clip_status(self, clip_id: int, status: str) -> None:
        """Обновляет статус клипа."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE clips SET status = ? WHERE id = ?",
                (status, clip_id),
            )

    async def update_clip_paths(
        self,
        clip_id: int,
        raw_clip_path: str | None = None,
        final_clip_path: str | None = None,
        subtitle_path: str | None = None,
    ) -> None:
        """Обновляет пути к файлам клипа."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                UPDATE clips
                SET raw_clip_path = COALESCE(?, raw_clip_path),
                    final_clip_path = COALESCE(?, final_clip_path),
                    subtitle_path = COALESCE(?, subtitle_path)
                WHERE id = ?
                """,
                (raw_clip_path, final_clip_path, subtitle_path, clip_id),
            )

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    async def add_job(
        self,
        job_type: str,
        video_id: int | None = None,
        clip_id: int | None = None,
        requires_gpu: bool = False,
        priority: int = 0,
    ) -> int:
        """Добавляет задачу в очередь, возвращает job_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO jobs (video_id, clip_id, job_type, requires_gpu, priority)
                VALUES (?, ?, ?, ?, ?)
                """,
                (video_id, clip_id, job_type, requires_gpu, priority),
            )
            return cursor.lastrowid

    async def get_next_job(
        self,
        job_type: str | None = None,
        requires_gpu: bool | None = None,
    ) -> dict | None:
        """
        Берёт самую старую задачу со статусом queued, помечает её как running.
        Возвращает словарь с данными задачи или None если очередь пуста.
        """
        async with self._get_connection() as conn:
            conditions = ["status = 'queued'"]
            params: list[Any] = []

            if job_type is not None:
                conditions.append("job_type = ?")
                params.append(job_type)
            if requires_gpu is not None:
                conditions.append("requires_gpu = ?")
                params.append(requires_gpu)

            where = " AND ".join(conditions)
            cursor = await conn.execute(
                f"SELECT * FROM jobs WHERE {where} ORDER BY priority DESC, created_at ASC LIMIT 1",
                params,
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            job = dict(row)
            await conn.execute(
                """
                UPDATE jobs
                SET status = 'running', started_at = CURRENT_TIMESTAMP, attempts = attempts + 1
                WHERE id = ?
                """,
                (job["id"],),
            )
            job["status"] = "running"
            return job

    async def update_job_status(
        self,
        job_id: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Обновляет статус задачи."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = ?,
                    completed_at = CASE WHEN ? IN ('completed', 'failed', 'cancelled')
                                        THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ?
                """,
                (status, error_message, status, job_id),
            )

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    async def add_source(
        self,
        chat_id: int,
        chat_title: str | None = None,
        chat_username: str | None = None,
    ) -> None:
        """Добавляет канал-источник (игнорирует дубли по chat_id)."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO sources (chat_id, chat_title, chat_username)
                VALUES (?, ?, ?)
                """,
                (chat_id, chat_title, chat_username),
            )

    async def get_active_sources(self) -> list[dict]:
        """Возвращает список активных каналов-источников."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sources WHERE is_active = TRUE"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Publications
    # ------------------------------------------------------------------

    async def add_publication(
        self,
        clip_id: int,
        platform: str,
        platform_post_id: str | None = None,
    ) -> int:
        """Добавляет запись о публикации, возвращает publication_id."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO publications (clip_id, platform, platform_post_id)
                VALUES (?, ?, ?)
                """,
                (clip_id, platform, platform_post_id),
            )
            return cursor.lastrowid

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Возвращает значение настройки по ключу или default."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """Устанавливает или обновляет значение настройки."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    # ------------------------------------------------------------------
    # Sources (дополнительные методы)
    # ------------------------------------------------------------------

    async def remove_source(self, chat_id: int) -> bool:
        """Удалить канал-источник. Возвращает True если удалён."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM sources WHERE chat_id = ?", (chat_id,)
            )
            return cursor.rowcount > 0

    async def increment_video_count(self, chat_id: int) -> None:
        """Увеличить счётчик видео для канала-источника."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE sources SET video_count = video_count + 1 WHERE chat_id = ?",
                (chat_id,),
            )

    # ------------------------------------------------------------------
    # Videos (дополнительные методы для Stage 2b)
    # ------------------------------------------------------------------

    async def get_video_counts_by_status(self) -> dict[str, int]:
        """Количество видео по статусам. Для /status команды."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
            )
            rows = await cursor.fetchall()
            return {row["status"]: row["cnt"] for row in rows}

    async def get_pending_jobs_count(self) -> int:
        """Количество задач в очереди (status=queued)."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'queued'"
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0

    async def update_video_buffer_message(self, video_id: int, buffer_message_id: int) -> None:
        """Сохранить ID сообщения в Buffer-канале."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE videos SET buffer_message_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (buffer_message_id, video_id),
            )

    async def get_videos_for_cleanup(self, hours: int) -> list[dict]:
        """Видео для авто-очистки: финальный статус + файл есть + старше N часов."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, file_path FROM videos
                WHERE status IN ('published', 'rejected', 'failed', 'skipped')
                AND file_path IS NOT NULL
                AND updated_at < datetime('now', ? || ' hours')
                """,
                (f"-{hours}",),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_video_file(self, video_id: int) -> None:
        """Очистить путь к файлу видео (после удаления файла)."""
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE videos SET file_path = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (video_id,),
            )
