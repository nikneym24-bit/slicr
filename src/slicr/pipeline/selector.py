"""
AI-отбор лучшего момента из транскрипции.

Использует Claude API для анализа транскрипции и выбора самого
вирального фрагмента длительностью 15–60 секунд.
"""

import json
import logging

from slicr.config import Config
from slicr.constants import JobStatus, VideoStatus
from slicr.database import Database
from slicr.services.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class MomentSelector:
    """AI-отбор момента через Claude API."""

    def __init__(self, config: Config, db: Database, claude: ClaudeClient) -> None:
        self.config = config
        self.db = db
        self.claude = claude

    async def select_moment(self, video_id: int, transcription_id: int) -> int | None:
        """
        Выбрать лучший фрагмент из транскрипции.

        Получает транскрипцию из БД, отправляет в Claude API,
        сохраняет результат как clip в БД.

        Returns:
            clip_id или None если подходящий момент не найден.
        """
        if self.config.mock_selector:
            logger.info(f"[MOCK] MomentSelector: video_id={video_id}")
            return None

        # Получаем видео и транскрипцию
        video = await self.db.get_video(video_id)
        if not video:
            logger.error(f"Видео {video_id} не найдено")
            return None

        async with self.db._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transcriptions WHERE id = ?",
                (transcription_id,),
            )
            row = await cursor.fetchone()
            transcription = dict(row) if row else None

        if not transcription:
            logger.error(f"Транскрипция {transcription_id} не найдена")
            return None

        # Формируем транскрипт с таймкодами для Claude
        transcript_text = transcription["full_text"]
        if transcription.get("segments_json"):
            segments = json.loads(transcription["segments_json"])
            lines = []
            for seg in segments:
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                text = seg.get("text", "").strip()
                lines.append(f"[{start:.1f}-{end:.1f}] {text}")
            transcript_text = "\n".join(lines)

        duration = video.get("duration", 0) or 0

        # Обновляем статус
        await self.db.update_video_status(video_id, VideoStatus.SELECTING)

        # Вызываем Claude API
        result = await self.claude.analyze_transcript(transcript_text, duration)

        if result is None:
            await self.db.update_video_status(video_id, VideoStatus.SKIPPED)
            logger.info(f"Видео {video_id}: подходящий момент не найден")
            return None

        # Сохраняем клип в БД
        clip_id = await self.db.add_clip(
            video_id=video_id,
            transcription_id=transcription_id,
            start_time=float(result["start_time"]),
            end_time=float(result["end_time"]),
            duration=float(result["end_time"]) - float(result["start_time"]),
            title=result.get("title"),
            description=result.get("description"),
            ai_reason=result.get("reason"),
            ai_score=float(result.get("score", 0)),
            transcript_fragment=transcript_text,
        )

        await self.db.update_video_status(video_id, VideoStatus.SELECTED)
        logger.info(
            f"Видео {video_id}: выбран клип {clip_id} "
            f"[{result['start_time']:.1f}-{result['end_time']:.1f}] "
            f"score={result.get('score', 0)}"
        )

        return clip_id
