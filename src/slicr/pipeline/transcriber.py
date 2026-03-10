"""
Транскрибатор речи через Groq Whisper API (pipeline-обёртка с БД).

Обёртка над TranscriptionService: читает видео из БД,
вызывает транскрибацию, сохраняет результат в БД.
"""

import json
import logging

from slicr.config import Config
from slicr.constants import VideoStatus
from slicr.database import Database
from slicr.services.transcription import TranscriberError, TranscriptionService

logger = logging.getLogger(__name__)

# Реэкспорт для обратной совместимости
__all__ = ["WhisperTranscriber", "TranscriberError"]


class WhisperTranscriber:
    """Транскрибация через Groq Whisper API (pipeline-обёртка с БД)."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db
        self._service = TranscriptionService(config)

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        await self._service.close()

    async def transcribe(self, video_id: int) -> int | None:
        """
        Транскрибировать видео.

        1. Получает видео из БД
        2. Вызывает TranscriptionService.transcribe()
        3. Сохраняет результат в БД

        Returns:
            transcription_id или None при ошибке.
        """
        import os

        video = await self.db.get_video(video_id)
        if not video:
            logger.error(f"Видео {video_id} не найдено")
            return None

        file_path = video.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Файл видео не найден: {file_path}")
            return None

        await self.db.update_video_status(video_id, VideoStatus.TRANSCRIBING)

        try:
            result = await self._service.transcribe(
                file_path, language=self.config.whisper_language
            )

            # Сериализуем для БД
            segments_json = (
                json.dumps(result.segments, ensure_ascii=False)
                if result.segments else None
            )
            words_json = (
                json.dumps(result.words, ensure_ascii=False)
                if result.words else None
            )

            transcription_id = await self.db.add_transcription(
                video_id=video_id,
                full_text=result.full_text,
                segments_json=segments_json,
                words_json=words_json,
                language=result.language,
                model_name=result.model_name,
                processing_time=result.processing_time,
            )

            await self.db.update_video_status(video_id, VideoStatus.TRANSCRIBED)
            logger.info(
                f"Видео {video_id}: транскрипция #{transcription_id} "
                f"({len(result.full_text)} символов, {len(result.segments)} сегментов, "
                f"{len(result.words)} слов, {result.processing_time:.1f}s)"
            )

            return transcription_id

        except TranscriberError as e:
            logger.error(f"Ошибка транскрибации видео {video_id}: {e}")
            await self.db.update_video_status(
                video_id, VideoStatus.FAILED, error_message=str(e)
            )
            return None

        except Exception as e:
            logger.error(f"Неожиданная ошибка транскрибации видео {video_id}: {e}")
            await self.db.update_video_status(
                video_id, VideoStatus.FAILED, error_message=str(e)
            )
            return None

    async def transcribe_file(self, audio_path: str, language: str = "ru") -> dict:
        """
        Транскрибировать аудиофайл напрямую (для тестов).

        Returns:
            Полный ответ Groq Whisper API.
        """
        return await self._service.call_whisper_api(audio_path, language=language)

    async def health_check(self) -> bool:
        """Проверить доступность Groq API."""
        return await self._service.health_check()
