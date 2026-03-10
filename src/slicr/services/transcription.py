"""
Сервис транскрибации через Groq Whisper API (без привязки к БД).

Извлекает аудио из видео через ffmpeg, отправляет в Groq Whisper API,
возвращает структурированный результат с word-level таймкодами.

Используется как VideoProcessor (GUI), так и WhisperTranscriber (pipeline).
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from slicr.config import Config

logger = logging.getLogger(__name__)

GROQ_API_BASE = "https://api.groq.com"
WHISPER_MODEL = "whisper-large-v3-turbo"

# Groq Whisper limits: 25 MB file size
MAX_AUDIO_SIZE = 25 * 1024 * 1024


class TranscriberError(Exception):
    """Ошибка транскрибации."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class TranscriptionResult:
    """Результат транскрибации."""

    full_text: str
    segments: list[dict] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    language: str = "ru"
    model_name: str = WHISPER_MODEL
    processing_time: float = 0.0


class TranscriptionService:
    """Транскрибация через Groq Whisper API (без БД)."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None

        if config.groq_proxy_url:
            self._base_url = config.groq_proxy_url.rstrip("/")
        else:
            self._base_url = GROQ_API_BASE

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def available(self) -> bool:
        """Есть ли API-ключ для транскрибации."""
        return bool(self.config.groq_api_key)

    async def extract_audio(self, video_path: str) -> str:
        """
        Извлечь аудио из видео через ffmpeg.

        Returns:
            Путь к аудиофайлу (.mp3).
        """
        audio_path = str(Path(video_path).with_suffix(".mp3"))

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "64k",
            audio_path,
        ]

        logger.info(f"Извлекаем аудио: {video_path} → {audio_path}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            error = stderr.decode(errors="replace")[-500:]
            raise TranscriberError(f"ffmpeg ошибка: {error}")

        file_size = os.path.getsize(audio_path)
        if file_size > MAX_AUDIO_SIZE:
            os.remove(audio_path)
            raise TranscriberError(
                f"Аудио слишком большое: {file_size / 1024 / 1024:.1f} MB "
                f"(лимит {MAX_AUDIO_SIZE / 1024 / 1024:.0f} MB)"
            )

        logger.info(f"Аудио извлечено: {file_size / 1024:.0f} KB")
        return audio_path

    async def call_whisper_api(
        self,
        audio_path: str,
        language: str = "ru",
        timeout: float = 120.0,
    ) -> dict:
        """
        Отправить аудио в Groq Whisper API.

        Returns:
            Ответ API с транскрипцией и таймкодами.
        """
        if not self.config.groq_api_key:
            raise TranscriberError("groq_api_key не настроен")

        url = f"{self._base_url}/openai/v1/audio/transcriptions"

        headers = {
            "Authorization": f"Bearer {self.config.groq_api_key}",
        }

        data = aiohttp.FormData()
        data.add_field(
            "file",
            open(audio_path, "rb"),
            filename=os.path.basename(audio_path),
            content_type="audio/mpeg",
        )
        data.add_field("model", WHISPER_MODEL)
        data.add_field("language", language)
        data.add_field("response_format", "verbose_json")
        data.add_field("timestamp_granularities[]", "segment")
        data.add_field("timestamp_granularities[]", "word")

        logger.info(f"Отправляем в Groq Whisper: {os.path.basename(audio_path)}")

        session = self._get_session()
        async with session.post(
            url,
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise TranscriberError(
                    f"Groq HTTP {response.status}: {error_text}",
                    status_code=response.status,
                )

            return await response.json()

    async def transcribe(
        self,
        video_path: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """
        Транскрибировать видео: извлечь аудио → Groq Whisper API → результат.

        Args:
            video_path: путь к видеофайлу.
            language: язык (по умолчанию из конфига).

        Returns:
            TranscriptionResult с текстом, сегментами и word-level данными.
        """
        lang = language or self.config.whisper_language
        audio_path = None
        start_time = time.time()

        try:
            audio_path = await self.extract_audio(video_path)
            result = await self.call_whisper_api(audio_path, language=lang)
            processing_time = time.time() - start_time

            return TranscriptionResult(
                full_text=result.get("text", ""),
                segments=result.get("segments", []),
                words=result.get("words", []),
                language=result.get("language", lang),
                model_name=WHISPER_MODEL,
                processing_time=processing_time,
            )

        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                logger.debug(f"Удалён временный файл: {audio_path}")

    async def health_check(self) -> bool:
        """Проверить доступность Groq API."""
        if not self.config.groq_api_key:
            return False

        url = f"{self._base_url}/openai/v1/models"
        headers = {
            "Authorization": f"Bearer {self.config.groq_api_key}",
        }

        try:
            session = self._get_session()
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False
