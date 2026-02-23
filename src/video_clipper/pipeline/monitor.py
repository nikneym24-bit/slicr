"""
Монитор Telegram-каналов.

Слушает source-каналы через Telethon, фильтрует входящие видео,
пересылает по цепочке Source → Buffer → Tech,
создаёт записи в БД со статусом queued.

Реализация: этап 2a.
"""

import asyncio
import logging
from typing import Callable

from video_clipper.config import Config
from video_clipper.constants import VideoStatus
from video_clipper.database import Database
from video_clipper.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

# Таймаут для сбора альбома (медиа-группы)
MEDIA_GROUP_TIMEOUT = 1.0  # секунд


class TelegramMonitor:
    """Мониторинг Telegram-каналов: фильтрация видео + пересылка Source→Buffer→Tech."""

    def __init__(
        self,
        config: Config,
        db: Database,
        tg_client: TelegramClientWrapper,
        on_new_video: Callable | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.tg_client = tg_client
        self._running = False
        self._on_new_video = on_new_video  # callback(video_id: int)
        # Кэш для сбора медиа-альбомов
        self._media_group_cache: dict[int, list] = {}
        self._media_group_tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        """Начать мониторинг."""
        if self.config.mock_monitor:
            logger.info("TelegramMonitor running in MOCK mode")
            return

        # Синхронизировать config.source_channels с БД
        await self._sync_sources()

        # Загрузить активные источники
        sources = await self.db.get_active_sources()
        source_ids = [s["chat_id"] for s in sources]

        if not source_ids:
            logger.warning("TelegramMonitor: нет активных источников, мониторинг не запущен")
            return

        # Зарегистрировать хэндлер новых сообщений
        @self.tg_client.on_new_message(chats=source_ids)
        async def handler(event):
            await self._handle_new_message(event)

        self._running = True
        logger.info(f"Monitoring {len(source_ids)} channels")

    async def stop(self) -> None:
        """Остановить мониторинг."""
        self._running = False
        # Отменить все pending задачи альбомов
        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_cache.clear()
        self._media_group_tasks.clear()
        logger.info("TelegramMonitor stopped")

    async def _handle_new_message(self, event) -> None:
        """
        Обработчик нового сообщения из канала-источника.

        Альбомы:
          - Если event.message.grouped_id is not None:
              - Добавить в _media_group_cache[grouped_id]
              - Отменить старый таск если есть
              - Создать новый таск с таймаутом MEDIA_GROUP_TIMEOUT
              - Таск вызывает _process_album(grouped_id)
          - Иначе: обработать как одиночное сообщение → _process_single(event)
        """
        try:
            grouped_id = getattr(event.message, "grouped_id", None)

            if grouped_id is not None:
                # Обработка медиа-группы (альбом)
                if grouped_id not in self._media_group_cache:
                    self._media_group_cache[grouped_id] = []

                # Отменить старый таск если новое сообщение пришло в ту же группу
                if grouped_id in self._media_group_tasks:
                    old_task = self._media_group_tasks[grouped_id]
                    if not old_task.done():
                        old_task.cancel()

                self._media_group_cache[grouped_id].append(event)

                # Создать новый таск с задержкой для сбора всей группы
                task = asyncio.create_task(self._delayed_process_album(grouped_id))
                self._media_group_tasks[grouped_id] = task

                logger.debug(
                    f"Добавлено в альбом {grouped_id}: "
                    f"{len(self._media_group_cache[grouped_id])} сообщений"
                )
            else:
                # Одиночное сообщение
                await self._process_single(event)

        except Exception as e:
            logger.error(f"Ошибка в _handle_new_message: {e}")

    async def _delayed_process_album(self, grouped_id: int) -> None:
        """Ждёт MEDIA_GROUP_TIMEOUT и обрабатывает собранный альбом."""
        await asyncio.sleep(MEDIA_GROUP_TIMEOUT)
        await self._process_album(grouped_id)

    async def _process_single(self, event) -> None:
        """
        Обработка одиночного сообщения (не альбом).

        Фильтры (проверять по порядку):
        1. Есть видео (именно video, не document/gif)
        2. Получить атрибуты видео
        3. duration >= config.min_video_duration
        4. duration <= config.max_video_duration
        5. file_size <= config.max_file_size
        6. _check_text_filter(caption)
        7. not await db.is_duplicate(chat_id, message_id)
        """
        message = event.message
        chat_id = event.chat_id
        message_id = message.id

        # 1. Проверяем наличие видео
        video_info = TelegramClientWrapper.extract_video_info(message)
        if video_info is None:
            logger.debug(f"Skipped msg {message_id}: no video")
            return

        duration = video_info["duration"]
        file_size = video_info["file_size"]
        width = video_info["width"]
        height = video_info["height"]

        # 2. Фильтр по длительности (мин)
        if duration < self.config.min_video_duration:
            logger.debug(
                f"Skipped msg {message_id}: duration {duration}s < {self.config.min_video_duration}s"
            )
            return

        # 3. Фильтр по длительности (макс)
        if duration > self.config.max_video_duration:
            logger.debug(
                f"Skipped msg {message_id}: duration {duration}s > {self.config.max_video_duration}s"
            )
            return

        # 4. Фильтр по размеру файла
        if file_size > self.config.max_file_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = self.config.max_file_size / (1024 * 1024)
            logger.debug(
                f"Skipped msg {message_id}: size {size_mb:.1f}MB > {max_mb:.1f}MB"
            )
            return

        # 5. Фильтр по тексту
        caption = message.message or None
        if not self._check_text_filter(caption):
            logger.debug(f"Skipped msg {message_id}: text filter rejected")
            return

        # 6. Проверка дубликата
        is_dup = await self.db.is_duplicate(chat_id, message_id)
        if is_dup:
            logger.debug(f"Skipped msg {message_id}: duplicate")
            return

        # Все фильтры пройдены — пересылаем
        size_mb = file_size / (1024 * 1024)
        logger.info(
            f"New video: chat={chat_id} msg={message_id} dur={duration}s size={size_mb:.1f}MB"
        )

        try:
            # 1. Переслать в Buffer с автором
            buffer_sent = await self.tg_client.forward_messages(
                to_chat_id=self.config.buffer_channel_id,
                from_chat_id=chat_id,
                message_ids=[message_id],
                drop_author=False,
            )
            buffer_message_id = buffer_sent[0].id if buffer_sent else None

            # 2. Переслать в Tech без автора
            await self.tg_client.forward_messages(
                to_chat_id=self.config.tech_channel_id,
                from_chat_id=chat_id,
                message_ids=[message_id],
                drop_author=True,
            )

            # 3. Отправить инфо-сообщение в Tech
            source_title = str(chat_id)
            await self.tg_client.send_message(
                self.config.tech_channel_id,
                f"📹 Канал: {source_title}\n⏱ {duration}с | 📦 {size_mb:.1f}MB",
            )

            # 4. Сохранить в БД
            video_id = await self.db.add_video(
                source_chat_id=chat_id,
                source_message_id=message_id,
                duration=float(duration),
                caption=caption,
                file_size=file_size,
                width=width,
                height=height,
            )

            # 4a. Сохранить buffer_message_id
            if buffer_message_id:
                await self.db.update_video_buffer_message(video_id, buffer_message_id)

            # 5. Уведомить о новом видео (callback для aiogram-бота)
            if self._on_new_video:
                await self._on_new_video(video_id)

        except Exception as e:
            logger.error(f"Ошибка при обработке msg {message_id}: {e}")

    async def _process_album(self, grouped_id: int) -> None:
        """
        Обработка альбома (медиа-группы).

        1. Извлечь события из кэша
        2. Отфильтровать: оставить только события с видео, прошедшие фильтры
        3. Если есть подходящие видео:
           - Переслать ВСЮ группу в Buffer с автором
           - Переслать ВСЮ группу в Tech без автора
           - Отправить инфо в Tech
           - Для каждого видео: db.add_video()
        4. Очистить _media_group_tasks[grouped_id]
        """
        events = self._media_group_cache.pop(grouped_id, [])
        self._media_group_tasks.pop(grouped_id, None)

        if not events:
            return

        # Сортируем по ID сообщения
        events = sorted(events, key=lambda e: e.message.id)

        # Фильтруем: только видео, прошедшие все фильтры
        valid_events = []
        for event in events:
            message = event.message
            video_info = TelegramClientWrapper.extract_video_info(message)
            if video_info is None:
                continue

            duration = video_info["duration"]
            file_size = video_info["file_size"]

            if duration < self.config.min_video_duration:
                continue
            if duration > self.config.max_video_duration:
                continue
            if file_size > self.config.max_file_size:
                continue

            caption = message.message or None
            if not self._check_text_filter(caption):
                continue

            chat_id = event.chat_id
            message_id = message.id
            is_dup = await self.db.is_duplicate(chat_id, message_id)
            if is_dup:
                continue

            valid_events.append((event, video_info))

        if not valid_events:
            logger.debug(f"Альбом {grouped_id}: нет подходящих видео")
            return

        # Берём данные из первого события для пересылки всей группы
        first_event = valid_events[0][0]
        chat_id = first_event.chat_id
        all_message_ids = [e.message.id for e, _ in valid_events]
        source_title = str(chat_id)

        logger.info(
            f"New album {grouped_id}: chat={chat_id} "
            f"{len(valid_events)} videos, msg_ids={all_message_ids}"
        )

        try:
            # 1. Переслать ВСЮ группу в Buffer с автором
            buffer_sent = await self.tg_client.forward_messages(
                to_chat_id=self.config.buffer_channel_id,
                from_chat_id=chat_id,
                message_ids=all_message_ids,
                drop_author=False,
            )

            # 2. Переслать ВСЮ группу в Tech без автора
            await self.tg_client.forward_messages(
                to_chat_id=self.config.tech_channel_id,
                from_chat_id=chat_id,
                message_ids=all_message_ids,
                drop_author=True,
            )

            # 3. Отправить инфо в Tech
            await self.tg_client.send_message(
                self.config.tech_channel_id,
                f"📹 Альбом ({len(valid_events)} видео) | Канал: {source_title}",
            )

            # 4. Сохранить каждое видео в БД
            for i, (event, video_info) in enumerate(valid_events):
                message = event.message
                caption = message.message or None
                try:
                    video_id = await self.db.add_video(
                        source_chat_id=chat_id,
                        source_message_id=message.id,
                        duration=float(video_info["duration"]),
                        caption=caption,
                        file_size=video_info["file_size"],
                        width=video_info["width"],
                        height=video_info["height"],
                    )
                    # Сохранить buffer_message_id (порядок buffer_sent совпадает с all_message_ids)
                    if buffer_sent and i < len(buffer_sent):
                        await self.db.update_video_buffer_message(video_id, buffer_sent[i].id)
                    # Уведомить о новом видео (callback для aiogram-бота)
                    if self._on_new_video:
                        await self._on_new_video(video_id)
                except Exception as e:
                    logger.error(f"Ошибка сохранения в БД msg {message.id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при обработке альбома {grouped_id}: {e}")

    def _check_text_filter(self, caption: str | None) -> bool:
        """
        Проверка текста по whitelist/blacklist.

        - Если config.filter_keywords не пустой:
            caption должен содержать хотя бы одно ключевое слово (регистронезависимо)
        - Если config.filter_stopwords не пустой:
            caption НЕ должен содержать стоп-слова
        - Если оба пустые — пропускаем всё (no filter)
        - Если caption is None — считаем пустой строкой

        return True если пост проходит фильтр
        """
        text = (caption or "").lower()

        # Проверка whitelist
        if self.config.filter_keywords:
            has_keyword = any(kw.lower() in text for kw in self.config.filter_keywords)
            if not has_keyword:
                return False

        # Проверка blacklist
        if self.config.filter_stopwords:
            has_stopword = any(sw.lower() in text for sw in self.config.filter_stopwords)
            if has_stopword:
                return False

        return True

    async def _sync_sources(self) -> None:
        """
        Синхронизирует config.source_channels с БД.
        Для каждого chat_id из конфига: await db.add_source(chat_id)
        (add_source использует INSERT OR IGNORE — дубли безопасны)
        """
        for chat_id in self.config.source_channels:
            await self.db.add_source(chat_id)
        if self.config.source_channels:
            logger.info(
                f"Синхронизировано {len(self.config.source_channels)} источников из конфига"
            )
