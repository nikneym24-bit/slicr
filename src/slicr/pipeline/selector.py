"""
AI-отбор лучших моментов из транскрипции.

Использует Claude API для анализа транскрипции и выбора
вирусных фрагментов длительностью 15–60 секунд.
Claude сам определяет количество моментов.
"""

import json
import logging

from slicr.config import Config
from slicr.constants import VideoStatus
from slicr.database import Database
from slicr.services.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class MomentSelector:
    """AI-отбор моментов через Claude API."""

    def __init__(self, config: Config, db: Database, claude: ClaudeClient) -> None:
        self.config = config
        self.db = db
        self.claude = claude

    async def select_moments(self, video_id: int, transcription_id: int) -> list[int]:
        """
        Выбрать лучшие фрагменты из транскрипции.

        Claude сам определяет количество моментов.
        Каждый момент сохраняется как отдельный clip в БД.

        Returns:
            Список clip_id. Пустой если ничего не найдено.
        """
        if self.config.mock_selector:
            logger.info(f"[MOCK] MomentSelector: video_id={video_id}")
            return []

        # Получаем видео и транскрипцию
        video = await self.db.get_video(video_id)
        if not video:
            logger.error(f"Видео {video_id} не найдено")
            return []

        async with self.db._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM transcriptions WHERE id = ?",
                (transcription_id,),
            )
            row = await cursor.fetchone()
            transcription = dict(row) if row else None

        if not transcription:
            logger.error(f"Транскрипция {transcription_id} не найдена")
            return []

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

        # Вызываем Claude API — возвращает список моментов
        moments = await self.claude.analyze_transcript(transcript_text, duration)

        if not moments:
            await self.db.update_video_status(video_id, VideoStatus.SKIPPED)
            logger.info(f"Видео {video_id}: подходящие моменты не найдены")
            return []

        # Сохраняем каждый момент как отдельный клип
        clip_ids: list[int] = []
        for moment in moments:
            clip_id = await self.db.add_clip(
                video_id=video_id,
                transcription_id=transcription_id,
                start_time=float(moment["start_time"]),
                end_time=float(moment["end_time"]),
                duration=float(moment["end_time"]) - float(moment["start_time"]),
                title=moment.get("title"),
                description=moment.get("description"),
                ai_reason=moment.get("reason"),
                ai_score=float(moment.get("score", 0)),
                transcript_fragment=transcript_text,
            )
            clip_ids.append(clip_id)
            logger.info(
                f"Видео {video_id}: клип {clip_id} "
                f"[{moment['start_time']:.1f}-{moment['end_time']:.1f}] "
                f"score={moment.get('score', 0)}"
            )

        await self.db.update_video_status(video_id, VideoStatus.SELECTED)
        logger.info(f"Видео {video_id}: выбрано {len(clip_ids)} клипов")

        return clip_ids
