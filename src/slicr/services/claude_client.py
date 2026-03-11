"""
Клиент Claude API для AI-отбора моментов.

Отправляет транскрипцию в Claude API и получает структурированный JSON
с выбранным фрагментом: start_time, end_time, title, reason, score.

Поддерживает прокси через Cloudflare Worker (claude_proxy_url в конфиге).
"""

import asyncio
import json
import logging
import subprocess
import sys
import tempfile
import time
from typing import Any

from slicr.config import Config

logger = logging.getLogger(__name__)

# На Windows нужен curl.exe чтобы не попасть на PowerShell-алиас
CURL_CMD = "curl.exe" if sys.platform == "win32" else "curl"

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
    """Клиент Claude API с поддержкой Cloudflare-прокси (через curl)."""

    def __init__(self, config: Config) -> None:
        self.config = config

        # Определяем base_url: прокси или прямой доступ
        if config.claude_proxy_url:
            self._base_url = config.claude_proxy_url.rstrip("/")
        else:
            self._base_url = ANTHROPIC_API_BASE

        # Rate limiter: timestamps запросов за последнюю минуту
        self._request_timestamps: list[float] = []
        self._rate_lock = asyncio.Lock()
        self._max_rpm = 50  # Anthropic tier 1 limit

    async def close(self) -> None:
        """Заглушка для совместимости (curl не требует сессий)."""
        pass

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
        Вызов Claude Messages API через curl с retry.

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

        url = f"{self._base_url}/v1/messages"

        last_error: ClaudeAPIError | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                status_code, body = await self._curl_post_json(
                    url, payload, timeout=timeout,
                )

                if status_code != 200:
                    err = ClaudeAPIError(
                        f"Claude HTTP {status_code}: {body[:500]}",
                        status_code=status_code,
                    )
                    if status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                        delay = _BASE_DELAY * (2 ** attempt)
                        logger.warning(
                            f"Claude ошибка (попытка {attempt + 1}): {err}, "
                            f"retry через {delay}s"
                        )
                        last_error = err
                        await asyncio.sleep(delay)
                        continue
                    raise err

                data = json.loads(body)

                # Извлекаем текст из ответа
                try:
                    text = data["content"][0]["text"]
                except (KeyError, IndexError) as e:
                    raise ClaudeAPIError(
                        f"Некорректная структура ответа: {e}"
                    )

                return self._parse_json(text)

            except json.JSONDecodeError as e:
                raise ClaudeAPIError(f"Некорректный JSON от API: {e}")
            except ClaudeAPIError:
                raise
            except Exception as e:
                last_error = ClaudeAPIError(f"Claude ошибка: {e}")
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Ошибка (попытка {attempt + 1}): {e}, retry через {delay}s")
                    await asyncio.sleep(delay)
                    continue
                raise last_error

        raise last_error  # type: ignore[misc]

    async def _curl_post_json(
        self,
        url: str,
        payload: dict,
        timeout: float = 30.0,
    ) -> tuple[int, str]:
        """Выполнить POST-запрос через curl, вернуть (status_code, body)."""
        payload_json = json.dumps(payload, ensure_ascii=False)

        # Пишем body в temp-файл чтобы избежать проблем с экранированием
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as tmp_payload:
            tmp_payload.write(payload_json)
            payload_path = tmp_payload.name

        # Temp-файл для ответа (избегаем проблем с \r\n на Windows)
        tmp_response = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False,
        )
        response_path = tmp_response.name
        tmp_response.close()

        cmd = [
            CURL_CMD, "-s",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-H", f"x-api-key: {self.config.claude_api_key}",
            "-H", f"anthropic-version: {ANTHROPIC_VERSION}",
            "-H", "Expect:",
            "-d", f"@{payload_path}",
            "-o", response_path,
            "-w", "%{http_code}",
            "--max-time", str(int(timeout)),
        ]

        if self.config.http_proxy:
            cmd.extend(["--proxy", self.config.http_proxy, "--proxy-basic"])

        cmd.append(url)

        try:
            def _run() -> tuple[int, str]:
                import os
                try:
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=timeout + 5,
                    )
                    status_str = result.stdout.decode().strip()
                    status = int(status_str) if status_str.isdigit() else 0

                    with open(response_path, "r", encoding="utf-8") as f:
                        body = f.read()

                    return status, body
                finally:
                    for p in (payload_path, response_path):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

            return await asyncio.to_thread(_run)

        except subprocess.TimeoutExpired:
            import os
            for p in (payload_path, response_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            raise ClaudeAPIError(f"Claude таймаут ({timeout}s)")

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
    ) -> list[dict[str, Any]]:
        """
        Анализировать транскрипцию и выбрать лучшие фрагменты.

        Claude сам определяет количество моментов в зависимости от
        длительности и качества контента.

        Args:
            transcript: Текст транскрипции с таймкодами
            duration: Полная длительность видео в секундах

        Returns:
            Список словарей с полями: start_time, end_time, title,
            description, reason, score. Пустой список если ничего не найдено.
        """
        min_clip = self.config.min_clip_duration
        max_clip = self.config.max_clip_duration

        system = (
            "Ты — эксперт по вирусному видеоконтенту. "
            "Твоя задача — найти самые захватывающие фрагменты из транскрипции видео "
            "для вертикальных клипов (9:16). "
            "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток."
        )

        prompt = (
            f"Проанализируй транскрипцию видео (длительность: {duration:.0f} сек) "
            f"и выбери ВСЕ подходящие вирусные фрагменты.\n\n"
            f"Ориентир по длительности: {min_clip}-{max_clip} секунд, "
            "но ГЛАВНОЕ — законченная мысль. Если фраза или идея завершается "
            f"на {max_clip + 5}-{max_clip + 15} секунде — включи её целиком. "
            "Не обрезай на полуслове. Лучше чуть длиннее, но с завершённой мыслью.\n\n"
            "Сам определи сколько фрагментов выбрать — от 0 до 10. "
            "Критерии: эмоциональность, законченная мысль, цепляющая фраза, "
            "интрига, юмор, конфликт. Не добавляй слабые моменты ради количества.\n\n"
            f"Транскрипция:\n{transcript}\n\n"
            'Верни JSON-объект с ключом "moments" — массив объектов:\n'
            '- "start_time": float (секунды начала)\n'
            '- "end_time": float (секунды конца)\n'
            '- "title": string (короткий цепляющий заголовок, по-русски)\n'
            '- "description": string (описание для публикации, 1-2 предложения)\n'
            '- "reason": string (почему этот фрагмент вирусный)\n'
            '- "score": float (оценка виральности от 0 до 100)\n'
            '- "keywords": list[string] (3-5 ключевых слов)\n\n'
            "Фрагменты НЕ должны пересекаться. Сортируй по score (лучший первый).\n\n"
            "Если подходящего контента нет, верни "
            '{"moments": [], "skip_reason": "причина"}.'
        )

        try:
            result = await self._call_api(
                messages=[{"role": "user", "content": prompt}],
                system=system,
                max_tokens=2048,
                temperature=0.3,
                timeout=60.0,
            )

            # Обработка формата с массивом moments
            moments_raw = result.get("moments", [])
            if not moments_raw:
                skip_reason = result.get("skip_reason", "нет подходящих моментов")
                logger.info(f"Claude пропустил видео: {skip_reason}")
                return []

            # Валидация каждого момента
            validated: list[dict[str, Any]] = []
            required = ["start_time", "end_time", "title", "reason", "score"]

            for i, moment in enumerate(moments_raw):
                missing = [f for f in required if f not in moment]
                if missing:
                    logger.warning(f"Момент {i}: нет полей {missing}, пропускаем")
                    continue

                start = float(moment["start_time"])
                end = float(moment["end_time"])
                clip_duration = end - start

                if start < 0 or end > duration + 1 or start >= end:
                    logger.warning(
                        f"Момент {i}: невалидные таймкоды {start:.1f}-{end:.1f}, пропускаем"
                    )
                    continue

                # Мягкая коррекция: только если слишком короткий
                if clip_duration < min_clip:
                    end = min(start + min_clip, duration)
                elif clip_duration > max_clip * 2:
                    # Отсекаем только совсем безумные длительности (>2x лимита)
                    logger.warning(
                        f"Момент {i}: {clip_duration:.0f}s > 2x лимита "
                        f"({max_clip}s), обрезаем"
                    )
                    end = start + max_clip
                moment["start_time"] = start
                moment["end_time"] = end

                validated.append(moment)

            # Убираем пересечения: оставляем момент с большим score
            validated = self._remove_overlaps(validated)

            logger.info(f"Claude выбрал {len(validated)} моментов из {len(moments_raw)}")
            return validated

        except ClaudeAPIError as e:
            logger.error(f"Ошибка Claude API: {e}")
            return []

    @staticmethod
    def _remove_overlaps(moments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Убрать пересекающиеся моменты, оставляя с большим score."""
        if not moments:
            return []

        # Сортируем по score (убывание)
        sorted_moments = sorted(moments, key=lambda m: float(m.get("score", 0)), reverse=True)
        accepted: list[dict[str, Any]] = []

        for moment in sorted_moments:
            start = float(moment["start_time"])
            end = float(moment["end_time"])
            overlaps = False
            for kept in accepted:
                ks = float(kept["start_time"])
                ke = float(kept["end_time"])
                if start < ke and end > ks:
                    overlaps = True
                    break
            if not overlaps:
                accepted.append(moment)

        # Возвращаем отсортированными по score
        return accepted

    async def health_check(self) -> bool:
        """Проверить доступность Claude API через прокси."""
        if not self.config.claude_api_key:
            return False

        if not await self._check_rate_limit():
            return False

        payload = {
            "model": self.config.claude_model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Reply: ok"}],
        }
        url = f"{self._base_url}/v1/messages"

        try:
            status_code, _ = await self._curl_post_json(url, payload, timeout=10.0)
            return status_code == 200
        except Exception:
            return False
