"""
Единая точка входа обработки видео (без БД).

VideoProcessor — полный конвейер:
  транскрибация → AI-отбор момента → нарезка → кроп 9:16 → субтитры.

Graceful degradation:
  - Нет groq_api_key → пропуск транскрибации
  - Нет claude_api_key → пропуск AI-отбора (берём всё видео)
  - Нет слов → пропуск субтитров
  - Кроп работает всегда
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from slicr.config import Config
from slicr.services.claude_client import ClaudeClient
from slicr.services.transcription import TranscriptionResult, TranscriptionService
from slicr.utils.subtitles import generate_ass
from slicr.utils.video import burn_subtitles, crop_to_vertical, extract_segment

logger = logging.getLogger(__name__)


@dataclass
class ProcessingOptions:
    """Опции обработки видео."""

    crop_enabled: bool = True
    crop_x_offset: float = 0.5
    subtitles_enabled: bool = True
    ai_select_enabled: bool = True
    max_clip_duration: int = 60
    min_clip_duration: int = 15
    language: str = "ru"


@dataclass
class ClipResult:
    """Результат одного клипа."""

    final_path: str
    title: str = ""
    score: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    subtitle_path: str | None = None


@dataclass
class ProcessingResult:
    """Результат обработки видео."""

    clips: list[ClipResult] = field(default_factory=list)
    transcript_text: str = ""
    words: list[dict] = field(default_factory=list)
    ai_selections: list[dict] = field(default_factory=list)
    steps_completed: list[str] = field(default_factory=list)

    @property
    def final_path(self) -> str:
        """Путь к первому клипу (обратная совместимость)."""
        return self.clips[0].final_path if self.clips else ""


ProgressCallback = Callable[[float, str], None]


class VideoProcessor:
    """
    Единая точка входа обработки видео.

    Используется GUI (без БД) и в будущем pipeline/orchestrator (с БД-обёрткой).
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._transcription = TranscriptionService(config)
        self._claude = ClaudeClient(config)

    async def close(self) -> None:
        """Закрыть HTTP-сессии."""
        await self._transcription.close()
        await self._claude.close()

    async def process(
        self,
        input_path: str,
        output_dir: str,
        options: ProcessingOptions | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ProcessingResult:
        """
        Обработать одно видео: полный конвейер.

        Шаги (каждый может быть пропущен при отсутствии ключей):
        1. Транскрибация (Groq Whisper) → текст + слова с таймкодами
        2. AI-отбор моментов (Claude) → массив {start_time, end_time, ...}
        3. Для каждого момента: нарезка → кроп 9:16 → субтитры

        Returns:
            ProcessingResult с клипами и метаданными.
        """
        if options is None:
            options = ProcessingOptions()

        stem = Path(input_path).stem
        os.makedirs(output_dir, exist_ok=True)

        steps: list[str] = []
        transcript_text = ""
        words: list[dict] = []
        ai_selections: list[dict] = []
        temp_files: list[str] = []

        def _progress(pct: float, msg: str) -> None:
            if on_progress:
                on_progress(pct, msg)

        try:
            # --- Шаг 1: Транскрибация ---
            transcription: TranscriptionResult | None = None
            if self._transcription.available:
                _progress(0.05, "Транскрибация: извлечение аудио...")
                try:
                    transcription = await self._transcription.transcribe(
                        input_path, language=options.language
                    )
                    transcript_text = transcription.full_text
                    words = transcription.words
                    steps.append("transcription")
                    _progress(0.30, f"Транскрибация завершена: {len(words)} слов")
                    logger.info(
                        "Транскрибация: %d символов, %d слов, %.1fs",
                        len(transcript_text), len(words),
                        transcription.processing_time,
                    )
                except Exception as e:
                    logger.error("Ошибка транскрибации: %s", e)
                    _progress(0.30, f"Транскрибация пропущена: {e}")
            else:
                _progress(0.30, "Транскрибация пропущена (нет API-ключа Groq)")

            # --- Шаг 2: AI-отбор моментов ---
            if (
                options.ai_select_enabled
                and self._claude_available
                and transcript_text
            ):
                _progress(0.35, "AI-отбор лучших моментов...")
                try:
                    duration = await self._get_duration(input_path)
                    ai_selections = await self._select_moments(
                        transcript_text,
                        transcription,
                        duration,
                        options,
                    )
                    if ai_selections:
                        steps.append("ai_selection")
                        _progress(
                            0.45,
                            f"AI выбрал {len(ai_selections)} моментов",
                        )
                    else:
                        _progress(0.45, "AI не нашёл подходящих моментов, берём всё видео")
                except Exception as e:
                    logger.error("Ошибка AI-отбора: %s", e)
                    _progress(0.45, f"AI-отбор пропущен: {e}")
            else:
                if not transcript_text:
                    _progress(0.45, "AI-отбор пропущен (нет транскрипции)")
                elif not self._claude_available:
                    _progress(0.45, "AI-отбор пропущен (нет API-ключа Claude)")

            # --- Шаг 3: Обработка каждого момента (или всего видео) ---
            clips: list[ClipResult] = []

            if not ai_selections:
                # Нет AI-отбора — обрабатываем всё видео как один клип
                clip = await self._process_single_clip(
                    input_path=input_path,
                    output_dir=output_dir,
                    stem=f"{stem}_slicr",
                    words=words,
                    options=options,
                    on_progress=_progress,
                    pct_start=0.50,
                    pct_end=1.0,
                    temp_files=temp_files,
                )
                if clip:
                    clips.append(clip)
            else:
                # Обрабатываем каждый момент
                total = len(ai_selections)
                for idx, moment in enumerate(ai_selections):
                    start_time = float(moment["start_time"])
                    end_time = float(moment["end_time"])
                    clip_stem = f"{stem}_clip{idx + 1}"
                    moment_words = self._shift_words(words, start_time, end_time)

                    pct_start = 0.45 + (0.55 * idx / total)
                    pct_end = 0.45 + (0.55 * (idx + 1) / total)

                    _progress(
                        pct_start,
                        f"Клип {idx + 1}/{total}: "
                        f"[{start_time:.1f}-{end_time:.1f}] "
                        f"{moment.get('title', '')}",
                    )

                    # Нарезка фрагмента
                    segment_path = os.path.join(output_dir, f"_segment_{clip_stem}.mp4")
                    temp_files.append(segment_path)

                    result = await extract_segment(
                        input_path, segment_path, start_time, end_time
                    )
                    if not result:
                        logger.warning(f"Не удалось вырезать клип {idx + 1}")
                        continue

                    clip = await self._process_single_clip(
                        input_path=segment_path,
                        output_dir=output_dir,
                        stem=clip_stem,
                        words=moment_words,
                        options=options,
                        on_progress=_progress,
                        pct_start=pct_start + (pct_end - pct_start) * 0.2,
                        pct_end=pct_end,
                        temp_files=temp_files,
                        title=moment.get("title", ""),
                        score=float(moment.get("score", 0)),
                        start_time=start_time,
                        end_time=end_time,
                    )
                    if clip:
                        clips.append(clip)
                        steps.append(f"clip_{idx + 1}")

            _progress(1.0, f"Готово! Создано клипов: {len(clips)}")

            return ProcessingResult(
                clips=clips,
                transcript_text=transcript_text,
                words=words,
                ai_selections=ai_selections,
                steps_completed=steps,
            )

        finally:
            # Очистка промежуточных файлов
            for temp in temp_files:
                if os.path.exists(temp):
                    os.remove(temp)
                    logger.debug("Удалён temp: %s", temp)

    async def _process_single_clip(
        self,
        input_path: str,
        output_dir: str,
        stem: str,
        words: list[dict],
        options: ProcessingOptions,
        on_progress: ProgressCallback,
        pct_start: float,
        pct_end: float,
        temp_files: list[str],
        title: str = "",
        score: float = 0.0,
        start_time: float = 0.0,
        end_time: float = 0.0,
    ) -> ClipResult | None:
        """Обработать один клип: кроп + субтитры."""
        cropped_path = os.path.join(output_dir, f"_cropped_{stem}.mp4")
        subtitle_path = os.path.join(output_dir, f"{stem}.ass")
        final_path = os.path.join(output_dir, f"{stem}.mp4")
        temp_files.append(cropped_path)

        current_path = input_path
        pct_range = pct_end - pct_start
        result_subtitle_path: str | None = None

        # Кроп в 9:16
        if options.crop_enabled:
            on_progress(pct_start, "Кроп в формат 9:16...")
            result = await crop_to_vertical(
                current_path, cropped_path,
                crop_x_offset=options.crop_x_offset,
            )
            if result:
                current_path = cropped_path
            else:
                logger.warning("Ошибка кропа, продолжаем без него")

        # Субтитры
        if options.subtitles_enabled and words:
            on_progress(pct_start + pct_range * 0.5, f"Генерация субтитров ({len(words)} слов)...")
            ass_path = generate_ass(words, subtitle_path)
            if ass_path:
                on_progress(pct_start + pct_range * 0.7, "Наложение субтитров на видео...")
                burn_result = await burn_subtitles(
                    current_path, ass_path, final_path
                )
                if burn_result:
                    result_subtitle_path = ass_path
                    on_progress(pct_end, "Субтитры наложены")
                else:
                    logger.warning("Не удалось наложить субтитры")
                    self._copy_to_final(current_path, final_path)
            else:
                self._copy_to_final(current_path, final_path)
        else:
            self._copy_to_final(current_path, final_path)

        if not os.path.exists(final_path):
            return None

        return ClipResult(
            final_path=final_path,
            title=title,
            score=score,
            start_time=start_time,
            end_time=end_time,
            subtitle_path=result_subtitle_path,
        )

    @property
    def _claude_available(self) -> bool:
        return bool(self._config.claude_api_key)

    async def _select_moments(
        self,
        transcript_text: str,
        transcription: TranscriptionResult | None,
        duration: float,
        options: ProcessingOptions,
    ) -> list[dict]:
        """Вызвать Claude API для отбора моментов."""
        # Формируем текст с таймкодами для Claude
        if transcription and transcription.segments:
            lines = []
            for seg in transcription.segments:
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                text = seg.get("text", "").strip()
                lines.append(f"[{start:.1f}-{end:.1f}] {text}")
            formatted = "\n".join(lines)
        else:
            formatted = transcript_text

        # Временно подменяем параметры длительности в конфиге
        orig_min = self._config.min_clip_duration
        orig_max = self._config.max_clip_duration
        try:
            self._config.min_clip_duration = options.min_clip_duration
            self._config.max_clip_duration = options.max_clip_duration
            return await self._claude.analyze_transcript(formatted, duration)
        finally:
            self._config.min_clip_duration = orig_min
            self._config.max_clip_duration = orig_max

    @staticmethod
    def _shift_words(
        words: list[dict], start_time: float, end_time: float
    ) -> list[dict]:
        """Отфильтровать слова в диапазоне клипа и сдвинуть таймкоды к нулю."""
        shifted = []
        for w in words:
            ws = w.get("start", 0)
            we = w.get("end", 0)
            # Включаем слова, которые хотя бы частично попадают в диапазон
            if we > start_time and ws < end_time:
                shifted.append({
                    "word": w.get("word", ""),
                    "start": max(0.0, ws - start_time),
                    "end": min(end_time - start_time, we - start_time),
                })
        return shifted

    @staticmethod
    def _copy_to_final(src: str, dst: str) -> None:
        """Скопировать/переместить файл на финальное место."""
        import shutil
        if src != dst:
            shutil.copy2(src, dst)

    @staticmethod
    async def _get_duration(path: str) -> float:
        """Получить длительность видео через ffprobe."""
        import asyncio as _asyncio

        proc = await _asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        try:
            return float(stdout.decode().strip())
        except (ValueError, AttributeError):
            return 0.0
