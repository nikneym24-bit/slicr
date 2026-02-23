"""
Загрузчик видео из Telegram Buffer-канала.

Подхватывает jobs типа DOWNLOAD, скачивает видео через TelegramClientWrapper,
обновляет статусы в БД.

Реализация: этап 2c.
"""

import asyncio
import logging
import os
from pathlib import Path

from video_clipper.config import Config
from video_clipper.constants import VideoStatus, JobType, JobStatus
from video_clipper.database import Database
from video_clipper.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

# Интервал проверки очереди (секунды)
POLL_INTERVAL = 5


class VideoDownloader:
    """Загрузка видео из Telegram Buffer-канала."""

    def __init__(self, config: Config, db: Database, tg_client: TelegramClientWrapper) -> None:
        self.config = config
        self.db = db
        self.tg_client = tg_client
        self._semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._running = False
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Запустить worker-цикл скачивания."""
        if self.config.mock_monitor:
            logger.info("VideoDownloader running in MOCK mode")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"VideoDownloader started (max concurrent: {self.config.max_concurrent_downloads})")

    async def stop(self) -> None:
        """Остановить worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("VideoDownloader stopped")

    async def _worker(self) -> None:
        """Основной worker-цикл."""
        while self._running:
            job = await self.db.get_next_job(job_type=JobType.DOWNLOAD)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            async with self._semaphore:
                await self._process_job(job)

    async def _process_job(self, job: dict) -> None:
        """Обработать одну задачу скачивания."""
        job_id = job["id"]
        video_id = job["video_id"]

        video = await self.db.get_video(video_id)
        if video is None:
            await self.db.update_job_status(job_id, JobStatus.FAILED, "Video not found")
            return

        await self.db.update_video_status(video_id, VideoStatus.DOWNLOADING)

        path = await self.download(video_id)

        if path:
            await self.db.update_job_status(job_id, JobStatus.COMPLETED)
        else:
            error_message = f"Не удалось скачать видео {video_id}"
            await self.db.update_job_status(job_id, JobStatus.FAILED, error_message)

            # Вернуть в очередь если есть попытки
            if job.get("attempts", 0) < job.get("max_attempts", 3):
                await self.db.update_job_status(job_id, JobStatus.QUEUED)
                logger.info(f"Job {job_id} возвращён в очередь (попытка {job['attempts']})")

    async def download(self, video_id: int) -> str | None:
        """
        Скачать видео по video_id.
        Возвращает путь к файлу или None при ошибке.
        """
        video = await self.db.get_video(video_id)
        if video is None:
            return None

        if self.config.mock_monitor:
            logger.info(f"MOCK: скачивание видео {video_id}")
            downloads_dir = Path(self.config.storage_base) / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            file_path = str(
                downloads_dir / f"{video_id}_{video['source_chat_id']}_{video['source_message_id']}.mp4"
            )
            Path(file_path).touch()
            await self.db.update_video_file(video_id, file_path, 0)
            await self.db.update_video_status(video_id, VideoStatus.DOWNLOADED)
            logger.info(f"MOCK: видео {video_id} → {file_path}")
            return file_path

        # Реальное скачивание
        source_chat_id = video["source_chat_id"]
        source_message_id = video["source_message_id"]
        buffer_message_id = video.get("buffer_message_id")

        downloads_dir = Path(self.config.storage_base) / "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        file_path = str(downloads_dir / f"{video_id}_{source_chat_id}_{source_message_id}.mp4")

        try:
            # Получить сообщение из Buffer или fallback на source
            message = None
            if buffer_message_id:
                messages = await self.tg_client.get_messages(
                    self.config.buffer_channel_id,
                    ids=[buffer_message_id],
                )
                message = messages[0] if messages else None

            if message is None:
                logger.warning(
                    f"Видео {video_id}: buffer_message_id не найден, fallback на source"
                )
                messages = await self.tg_client.get_messages(
                    source_chat_id,
                    ids=[source_message_id],
                )
                message = messages[0] if messages else None

            if message is None:
                logger.error(f"Видео {video_id}: сообщение не найдено ни в buffer, ни в source")
                await self.db.update_video_status(video_id, VideoStatus.FAILED, "Сообщение не найдено")
                return None

            result = await self.tg_client.download_media(
                message,
                file_path,
                progress_callback=self._make_progress_callback(video_id),
            )

            if result:
                file_size = os.path.getsize(result)
                await self.db.update_video_file(video_id, result, file_size)
                await self.db.update_video_status(video_id, VideoStatus.DOWNLOADED)
                logger.info(
                    f"Скачано видео {video_id}: {result} ({file_size / 1024 / 1024:.1f}MB)"
                )
                return result
            else:
                await self.db.update_video_status(video_id, VideoStatus.FAILED, "download_media вернул None")
                return None

        except Exception as e:
            await self.db.update_video_status(video_id, VideoStatus.FAILED, str(e))
            logger.error(f"Ошибка скачивания видео {video_id}: {e}")
            return None

    def _make_progress_callback(self, video_id: int):
        """Создать callback для логирования прогресса (каждые 10%)."""
        last_logged = [0]  # mutable для замыкания

        def callback(current: int, total: int) -> None:
            if total == 0:
                return
            percent = int(current / total * 100)
            if percent >= last_logged[0] + 10:
                last_logged[0] = percent
                current_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                logger.info(
                    f"Скачивание видео {video_id}: {percent}% ({current_mb:.1f}/{total_mb:.1f} MB)"
                )

        return callback

    async def cleanup_old_files(self) -> None:
        """Авто-очистка скачанных видео."""
        if not self.config.cleanup_enabled:
            return

        videos = await self.db.get_videos_for_cleanup(self.config.cleanup_after_hours)
        removed = 0
        for video in videos:
            file_path = video.get("file_path")
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    await self.db.clear_video_file(video["id"])
                    removed += 1
                except Exception as e:
                    logger.error(f"Ошибка удаления файла {file_path}: {e}")

        logger.info(f"Очищено {removed} старых видеофайлов")
