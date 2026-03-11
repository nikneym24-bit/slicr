"""
Сервис транскрибации через Groq Whisper API (без привязки к БД).

Извлекает аудио из видео через ffmpeg, отправляет в Groq Whisper API,
возвращает структурированный результат с word-level таймкодами.

Используется как VideoProcessor (GUI), так и WhisperTranscriber (pipeline).
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from slicr.config import Config

logger = logging.getLogger(__name__)

GROQ_API_BASE = "https://api.groq.com"

# На Windows нужен curl.exe чтобы не попасть на PowerShell-алиас
CURL_CMD = "curl.exe" if sys.platform == "win32" else "curl"
# /dev/null на Unix, NUL на Windows
DEV_NULL = "NUL" if sys.platform == "win32" else "/dev/null"
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
    """Транскрибация через Groq Whisper API (через curl)."""

    def __init__(self, config: Config) -> None:
        self.config = config

        if config.groq_proxy_url:
            self._base_url = config.groq_proxy_url.rstrip("/")
        else:
            self._base_url = GROQ_API_BASE

    async def close(self) -> None:
        """Заглушка для совместимости (curl не требует сессий)."""
        pass

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

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_data = await proc.communicate()
            returncode = proc.returncode or 0
            stderr_text = stderr_data.decode(errors="replace")
        except NotImplementedError:
            # Windows + uvicorn reload: event loop не поддерживает subprocess
            def _sync() -> tuple[int, str]:
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                return result.returncode, result.stderr.decode(errors="replace")

            returncode, stderr_text = await asyncio.to_thread(_sync)

        if returncode != 0:
            raise TranscriberError(f"ffmpeg ошибка: {stderr_text[-500:]}")

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
        Отправить аудио в Groq Whisper API через curl.

        Returns:
            Ответ API с транскрипцией и таймкодами.
        """
        if not self.config.groq_api_key:
            raise TranscriberError("groq_api_key не настроен")

        url = f"{self._base_url}/openai/v1/audio/transcriptions"

        logger.info(f"Отправляем в Groq Whisper: {os.path.basename(audio_path)}")

        # Temp-файл для ответа
        tmp_response = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        )
        response_path = tmp_response.name
        tmp_response.close()

        cmd = [
            CURL_CMD, "-s",
            "-X", "POST",
            "-H", f"Authorization: Bearer {self.config.groq_api_key}",
            "-H", "Expect:",
            "-F", f"file=@{audio_path}",
            "-F", f"model={WHISPER_MODEL}",
            "-F", f"language={language}",
            "-F", "response_format=verbose_json",
            "-F", "timestamp_granularities[]=segment",
            "-F", "timestamp_granularities[]=word",
            "-o", response_path,
            "-w", "%{http_code}",
            "--max-time", str(int(timeout)),
        ]

        if self.config.http_proxy:
            cmd.extend(["--proxy", self.config.http_proxy, "--proxy-basic"])

        cmd.append(url)

        def _run() -> tuple[int, str]:
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout + 10,
                )
                status_str = result.stdout.decode().strip()
                stderr_text = result.stderr.decode(errors="replace").strip()

                if stderr_text:
                    logger.debug("curl stderr: %s", stderr_text[:300])

                if not status_str.isdigit():
                    logger.error(
                        "curl вернул неожиданный stdout: %r (returncode=%d)",
                        status_str[:200], result.returncode,
                    )

                status = int(status_str) if status_str.isdigit() else 0

                with open(response_path, "r", encoding="utf-8") as f:
                    body = f.read()

                return status, body
            finally:
                try:
                    os.remove(response_path)
                except OSError:
                    pass

        try:
            status_code, body = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            try:
                os.remove(response_path)
            except OSError:
                pass
            raise TranscriberError(f"Groq таймаут ({timeout}s)")

        if status_code != 200:
            raise TranscriberError(
                f"Groq HTTP {status_code}: {body[:500]}",
                status_code=status_code,
            )

        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise TranscriberError(f"Некорректный JSON от Groq: {e}")

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
        """Проверить доступность Groq API через curl."""
        if not self.config.groq_api_key:
            return False

        url = f"{self._base_url}/openai/v1/models"

        cmd = [
            CURL_CMD, "-s",
            "-H", f"Authorization: Bearer {self.config.groq_api_key}",
            "-o", DEV_NULL,
            "-w", "%{http_code}",
            "--max-time", "10",
        ]

        if self.config.http_proxy:
            cmd.extend(["--proxy", self.config.http_proxy, "--proxy-basic"])

        cmd.append(url)

        def _run() -> int:
            try:
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                )
                status_str = result.stdout.decode().strip()
                return int(status_str) if status_str.isdigit() else 0
            except Exception:
                return 0

        try:
            status = await asyncio.to_thread(_run)
            return status == 200
        except Exception:
            return False
