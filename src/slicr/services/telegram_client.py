"""
Обёртка над Telethon для мониторинга Telegram-каналов.

Единственное место в проекте, где импортируется telethon.
Управляет подключением, сессией, пересылкой и скачиванием.

Реализация: этап 2a.
"""

import asyncio
import logging
from typing import Any, Callable

from slicr.config import Config

logger = logging.getLogger(__name__)


class TelegramClientWrapper:
    """
    Обёртка над Telethon: подключение, прокси, пересылка, скачивание.
    Единственное место в проекте, где импортируется telethon.
    """

    def __init__(self, config: Config) -> None:
        """
        Создаёт Telethon-клиент (НЕ подключается).

        Session:
        - Если config.session_string задан — StringSession
        - Иначе — файловая сессия "slicr" (создаст slicr.session)

        Proxy:
        - config.proxy = None → прямое подключение
        - config.proxy = {"type": "socks5", "host": "...", "port": ..., ...}
        - config.proxy = {"type": "mtproto", "host": "...", "port": ..., "secret": "..."}
        """
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        # Session
        if config.session_string:
            session = StringSession(config.session_string)
        else:
            session = "slicr"  # файл slicr.session

        # Proxy
        proxy = None
        connection = None  # для MTProxy

        if config.proxy:
            proxy_type = config.proxy.get("type", "")

            if proxy_type == "socks5":
                import socks
                proxy = (
                    socks.SOCKS5,
                    config.proxy["host"],
                    config.proxy["port"],
                    True,  # rdns
                    config.proxy.get("username"),
                    config.proxy.get("password"),
                )

            elif proxy_type == "mtproto":
                from telethon.network import connection as tl_conn
                connection = tl_conn.ConnectionTcpMTProxyRandomizedIntermediate
                proxy = (
                    config.proxy["host"],
                    config.proxy["port"],
                    config.proxy["secret"],
                )

        # Клиент
        # В mock-режиме (api_id == 0) Telethon-клиент не создаётся:
        # TelegramMonitor.start() вернётся досрочно и методы клиента не вызовутся.
        if not config.api_id:
            self._client = None
            logger.debug("TelegramClientWrapper: api_id=0, Telethon client not created (mock mode)")
            return

        kwargs: dict[str, Any] = {}
        if proxy:
            kwargs["proxy"] = proxy
        if connection:
            kwargs["connection"] = connection

        self._client = TelegramClient(session, config.api_id, config.api_hash, **kwargs)

    async def connect(self) -> None:
        """Подключиться к Telegram."""
        try:
            await self._client.start()
            me = await self._client.get_me()
            name = me.first_name or ""
            username = me.username or "без username"
            logger.info(f"Telethon authorized as: {name} (@{username})")
        except EOFError as e:
            raise RuntimeError(
                "Telethon не может авторизоваться интерактивно. "
                "Запустите scripts/generate_session.py для создания session_string."
            ) from e

    async def disconnect(self) -> None:
        """Отключиться от Telegram."""
        await self._client.disconnect()
        logger.info("Telethon disconnected")

    @property
    def client(self) -> Any:
        """
        Прямой доступ к Telethon-клиенту.
        Нужен для monitor.py — регистрации хэндлеров через on_new_message().
        Тип: telethon.TelegramClient (но в type hint — Any, чтобы не нарушать изоляцию).
        """
        return self._client

    def on_new_message(self, chats: list[int] | None = None):
        """
        Декоратор для регистрации хэндлера на новые сообщения.
        Обёртка над @client.on(events.NewMessage(chats=chats)).

        Использование в monitor.py:
            @tg_client.on_new_message(chats=source_ids)
            async def handler(event):
                ...

        Это позволяет monitor.py НЕ импортировать telethon (Правило 4).
        """
        from telethon import events
        return self._client.on(events.NewMessage(chats=chats))

    async def forward_messages(
        self,
        to_chat_id: int,
        from_chat_id: int,
        message_ids: list[int],
        drop_author: bool = False,
    ) -> list:
        """
        Переслать сообщения из одного чата в другой.
        Возвращает список отправленных сообщений.
        """
        result = await self._client.forward_messages(
            entity=to_chat_id,
            messages=message_ids,
            from_peer=from_chat_id,
            drop_author=drop_author,
        )
        # Telethon возвращает одно сообщение или список — нормализуем
        if not isinstance(result, list):
            return [result]
        return result

    async def send_message(self, chat_id: int, text: str) -> None:
        """Отправить текстовое сообщение (для инфо в Tech канал)."""
        await self._client.send_message(chat_id, text)

    async def download_media(
        self,
        message: Any,
        file_path: str,
        progress_callback: Callable | None = None,
    ) -> str | None:
        """
        Скачать медиа из сообщения.
        Обёрнуто в retry с exponential backoff (3 попытки).

        - progress_callback(current_bytes, total_bytes)
        - Возвращает путь к файлу или None при ошибке
        """
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                result = await self._client.download_media(
                    message, file=file_path, progress_callback=progress_callback
                )
                return result
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Download failed after {max_retries} attempts: {e}")
                    return None
                wait = 2 ** attempt  # 2, 4, 8 секунд
                logger.warning(f"Download attempt {attempt} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)
        return None

    async def get_entity(self, entity_id: int) -> Any:
        """Получить entity по ID (для валидации каналов)."""
        return await self._client.get_entity(entity_id)

    async def get_messages(self, chat_id: int, ids: list[int]) -> list:
        """Получить конкретные сообщения по ID."""
        result = await self._client.get_messages(chat_id, ids=ids)
        if not isinstance(result, list):
            return [result]
        return result

    @staticmethod
    def extract_video_info(message: Any) -> dict | None:
        """
        Извлечь информацию о видео из Telethon message.
        Возвращает dict с ключами: duration, width, height, file_size
        Или None если сообщение не содержит видео.
        """
        from telethon.tl.types import DocumentAttributeVideo

        video = message.video
        if video is None:
            return None

        duration = 0
        width = 0
        height = 0

        for attr in video.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                duration = attr.duration
                width = attr.w
                height = attr.h
                break

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "file_size": video.size or 0,
        }
