"""
Клиент Claude API для AI-отбора моментов.

Отправляет транскрипцию в Claude API и получает структурированный JSON
с выбранным фрагментом: start_time, end_time, title, reason, score.

Поддерживает прокси через Cloudflare Worker (claude_proxy_url в конфиге).
"""

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from slicr.config import Config

logger = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_BASE_DELAY = 1.0


class ClaudeAPIError(Exception):
    """Ошибка вызова Claude API."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ClaudeClient:
    """Клиент Claude API с поддержкой Cloudflare-прокси."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None

        # Определяем base_url: прокси или прямой доступ
        if config.claude_proxy_url:
            self._base_url = config.claude_proxy_url.rstrip("/")
        else:
            self._base_url = ANTHROPIC_API_BASE

        # Rate limiter: timestamps запросов за последнюю минуту
        self._request_timestamps: list[float] = []
        self._rate_lock = asyncio.Lock()
        self._max_rpm = 50  # Anthropic tier 1 limit

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _check_rate_limit(self) -> bool:
        """Проверить rate limit. Возвращает True если можно делать запрос."""
        async with self._rate_lock:
            now = time.time()
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > now - 60
            ]
            if len(self._request_timestamps) >= self._max_rpm:
                logger.warning(f"Rate limit: {self._max_rpm} req/min, пропускаем")
                return False
            self._request_timestamps.append(now)
            return True

    async def _call_api(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Вызов Claude Messages API с retry.

        Returns:
            Распарсенный JSON из ответа модели.
        """
        if not self.config.claude_api_key:
            raise ClaudeAPIError("claude_api_key не настроен")

        if not await self._check_rate_limit():
            raise ClaudeAPIError("Rate limit exceeded")

        payload: dict[str, Any] = {
            "model": self.config.claude_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.claude_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

        url = f"{self._base_url}/v1/messages"

        last_error: ClaudeAPIError | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                session = self._get_session()
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        err = ClaudeAPIError(
                            f"Claude HTTP {response.status}: {error_text}",
                            status_code=response.status,
                        )
                        if response.status in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                            delay = _BASE_DELAY * (2 ** attempt)
                            logger.warning(
                                f"Claude ошибка (попытка {attempt + 1}): {err}, "
                                f"retry через {delay}s"
                            )
                            last_error = err
                            await asyncio.sleep(delay)
                            continue
                        raise err

                    data = await response.json()

                    # Извлекаем текст из ответа
                    try:
                        text = data["content"][0]["text"]
                    except (KeyError, IndexError) as e:
                        raise ClaudeAPIError(
                            f"Некорректная структура ответа: {e}"
                        )

                    return self._parse_json(text)

            except asyncio.TimeoutError:
                last_error = ClaudeAPIError(f"Claude таймаут ({timeout}s)")
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Таймаут (попытка {attempt + 1}), retry через {delay}s")
                    await asyncio.sleep(delay)
                    continue
                raise last_error
            except aiohttp.ClientError as e:
                raise ClaudeAPIError(f"Claude HTTP ошибка: {e}")

        raise last_error  # type: ignore[misc]

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Извлечь JSON из ответа модели (убирает ```json ... ```)."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Не удалось распарсить JSON: {text[:200]}")
            raise ClaudeAPIError(f"Некорректный JSON в ответе: {e}")

    async def analyze_transcript(
        self,
        transcript: str,
        duration: float,
    ) -> dict[str, Any] | None:
        """
        Анализировать транскрипцию и выбрать лучший фрагмент.

        Args:
            transcript: Текст транскрипции с таймкодами
            duration: Полная длительность видео в секундах

        Returns:
            Словарь с полями: start_time, end_time, title, description,
            reason, score — или None если момент не найден.
        """
        min_clip = self.config.min_clip_duration
        max_clip = self.config.max_clip_duration

        system = (
            "Ты — эксперт по вирусному видеоконтенту. "
            "Твоя задача — найти самый захватывающий фрагмент из транскрипции видео "
            "для вертикального клипа (9:16). "
            "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток."
        )

        prompt = (
            f"Проанализируй транскрипцию видео (длительность: {duration:.0f} сек) "
            f"и выбери ОДИН самый вирусный фрагмент длительностью от {min_clip} до {max_clip} секунд.\n\n"
            f"Транскрипция:\n{transcript}\n\n"
            "Верни JSON с полями:\n"
            '- "start_time": float (секунды начала фрагмента)\n'
            '- "end_time": float (секунды конца фрагмента)\n'
            '- "title": string (короткий цепляющий заголовок для клипа, по-русски)\n'
            '- "description": string (описание клипа для публикации, 1-2 предложения)\n'
            '- "reason": string (почему этот фрагмент самый вирусный)\n'
            '- "score": float (оценка виральности от 0 до 100)\n'
            '- "keywords": list[string] (3-5 ключевых слов)\n\n'
            "Если в транскрипции нет подходящего контента, верни "
            '{"skip": true, "reason": "причина"}.'
        )

        try:
            result = await self._call_api(
                messages=[{"role": "user", "content": prompt}],
                system=system,
                max_tokens=512,
                temperature=0.3,
                timeout=30.0,
            )

            if result.get("skip"):
                logger.info(f"Claude пропустил видео: {result.get('reason')}")
                return None

            # Валидация обязательных полей
            required = ["start_time", "end_time", "title", "reason", "score"]
            missing = [f for f in required if f not in result]
            if missing:
                logger.error(f"Claude вернул неполный ответ, нет полей: {missing}")
                return None

            # Валидация таймкодов
            start = float(result["start_time"])
            end = float(result["end_time"])
            clip_duration = end - start

            if start < 0 or end > duration or start >= end:
                logger.error(f"Невалидные таймкоды: {start}-{end} (видео {duration}s)")
                return None

            if clip_duration < min_clip or clip_duration > max_clip:
                logger.warning(
                    f"Длина клипа {clip_duration:.1f}s вне диапазона "
                    f"[{min_clip}, {max_clip}], корректируем"
                )
                # Пытаемся скорректировать до допустимой длины
                if clip_duration < min_clip:
                    end = min(start + min_clip, duration)
                elif clip_duration > max_clip:
                    end = start + max_clip
                result["end_time"] = end

            return result

        except ClaudeAPIError as e:
            logger.error(f"Ошибка Claude API: {e}")
            return None

    async def health_check(self) -> bool:
        """Проверить доступность Claude API через прокси."""
        if not self.config.claude_api_key:
            return False

        if not await self._check_rate_limit():
            return False

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.claude_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        payload = {
            "model": self.config.claude_model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Reply: ok"}],
        }
        url = f"{self._base_url}/v1/messages"

        try:
            session = self._get_session()
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False
