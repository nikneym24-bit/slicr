"""
Видеоредактор — монтаж клипа.

Вырезает фрагмент, кропает в формат 9:16 (1080x1920),
накладывает субтитры. Кодирование CPU-only (libx264), без NVENC.
"""

import json
import logging
import os
from pathlib import Path

from slicr.config import Config
from slicr.database import Database
from slicr.utils.subtitles import generate_ass
from slicr.utils.video import burn_subtitles, crop_to_vertical, extract_segment

logger = logging.getLogger(__name__)


class VideoEditor:
    """Монтаж клипа через ffmpeg."""

    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

        # Убеждаемся что директории существуют
        self._clips_dir = Path(config.storage_base) / "clips"
        self._temp_dir = Path(config.storage_base) / "temp"
        self._clips_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    async def create_clip(self, clip_id: int) -> str | None:
        """
        Смонтировать финальный клип: вырезка + кроп 9:16 + субтитры.

        1. Вырезает сегмент по таймкодам
        2. Кропает в вертикальный формат 9:16
        3. Генерирует ASS-субтитры из word-level транскрипции
        4. Накладывает субтитры на видео

        Returns:
            Путь к готовому файлу или None при ошибке.
        """
        # Получаем данные клипа
        async with self.db._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM clips WHERE id = ?", (clip_id,)
            )
            row = await cursor.fetchone()
            clip = dict(row) if row else None

        if not clip:
            logger.error(f"Клип {clip_id} не найден")
            return None

        video_id = clip["video_id"]
        start_time = clip["start_time"]
        end_time = clip["end_time"]
        transcription_id = clip.get("transcription_id")

        # Получаем видео
        video = await self.db.get_video(video_id)
        if not video or not video.get("file_path"):
            logger.error(f"Видео {video_id} не найдено или нет файла")
            return None

        input_path = video["file_path"]
        if not os.path.exists(input_path):
            logger.error(f"Файл видео не найден: {input_path}")
            return None

        # Получаем words для субтитров
        words: list[dict] = []
        if transcription_id:
            async with self.db._get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT words_json FROM transcriptions WHERE id = ?",
                    (transcription_id,),
                )
                row = await cursor.fetchone()
                if row and row["words_json"]:
                    all_words = json.loads(row["words_json"])
                    # Фильтруем слова в диапазоне клипа, сдвигаем таймкоды
                    for w in all_words:
                        ws = w.get("start", 0)
                        we = w.get("end", 0)
                        # Включаем слова, частично попадающие в диапазон
                        if we > start_time and ws < end_time:
                            words.append({
                                "word": w.get("word", ""),
                                "start": max(0.0, ws - start_time),
                                "end": min(end_time - start_time, we - start_time),
                            })

        # Пути к промежуточным и финальным файлам
        segment_path = str(self._temp_dir / f"segment_{clip_id}.mp4")
        cropped_path = str(self._temp_dir / f"cropped_{clip_id}.mp4")
        subtitle_path = str(self._clips_dir / f"clip_{clip_id}.ass")
        final_path = str(self._clips_dir / f"clip_{clip_id}.mp4")

        await self.db.update_clip_status(clip_id, "processing")

        try:
            # 1. Вырезаем сегмент
            logger.info(f"Клип {clip_id}: вырезаем [{start_time:.1f}-{end_time:.1f}]")
            result = await extract_segment(input_path, segment_path, start_time, end_time)
            if not result:
                raise RuntimeError("extract_segment failed")

            # 2. Кроп в 9:16
            logger.info(f"Клип {clip_id}: кроп в 1080x1920")
            result = await crop_to_vertical(segment_path, cropped_path)
            if not result:
                raise RuntimeError("crop_to_vertical failed")

            # 3. Генерируем субтитры + накладываем
            if words:
                logger.info(f"Клип {clip_id}: генерируем субтитры ({len(words)} слов)")
                sub_result = generate_ass(words, subtitle_path)
                if sub_result:
                    logger.info(f"Клип {clip_id}: накладываем субтитры")
                    result = await burn_subtitles(cropped_path, subtitle_path, final_path)
                    if not result:
                        raise RuntimeError("burn_subtitles failed")
                else:
                    # Субтитры не удалось создать — используем видео без них
                    logger.warning(f"Клип {clip_id}: субтитры не созданы, используем без них")
                    os.rename(cropped_path, final_path)
                    cropped_path = None  # чтобы не удалять
            else:
                # Нет слов — используем видео без субтитров
                logger.info(f"Клип {clip_id}: нет word-level данных, без субтитров")
                os.rename(cropped_path, final_path)
                cropped_path = None

            # Обновляем БД
            await self.db.update_clip_paths(
                clip_id,
                raw_clip_path=segment_path if os.path.exists(segment_path) else None,
                final_clip_path=final_path,
                subtitle_path=subtitle_path if os.path.exists(subtitle_path) else None,
            )
            await self.db.update_clip_status(clip_id, "ready")

            logger.info(f"Клип {clip_id}: готов → {final_path}")
            return final_path

        except Exception as e:
            logger.error(f"Ошибка монтажа клипа {clip_id}: {e}")
            await self.db.update_clip_status(clip_id, "failed")
            return None

        finally:
            # Удаляем temp-файлы
            for temp in [segment_path, cropped_path]:
                if temp and os.path.exists(temp):
                    os.remove(temp)
                    logger.debug(f"Удалён temp: {temp}")
