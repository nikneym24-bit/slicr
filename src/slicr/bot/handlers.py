"""Команды Telegram-бота: /start, /help, /status, /sources, /add_source, /remove_source."""

import logging
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from slicr.database import Database
from slicr.services.telegram_client import TelegramClientWrapper

logger = logging.getLogger(__name__)

router = Router()

# Модуль-уровень переменные (устанавливаются через setup())
_db: Database | None = None
_tg_client: TelegramClientWrapper | None = None
_admin_id: int = 0


def setup(db: Database, tg_client: TelegramClientWrapper, admin_id: int) -> None:
    """Инициализация модуля с зависимостями."""
    global _db, _tg_client, _admin_id
    _db = db
    _tg_client = tg_client
    _admin_id = admin_id


def _is_admin(message: Message) -> bool:
    """Проверка что сообщение от админа."""
    return message.from_user is not None and message.from_user.id == _admin_id


def _parse_telegram_link(text: str) -> str | None:
    """
    Извлечь username из Telegram-ссылки.
    Поддерживает:
      - https://t.me/channel_name → channel_name
      - @channel_name → channel_name
      - channel_name → channel_name
    Возвращает username без @ или None.
    """
    text = text.strip()

    # https://t.me/channel_name или https://t.me/+invite
    match = re.match(r'https?://t\.me/(?:\+)?(\w+)', text)
    if match:
        return match.group(1)

    # @channel_name
    if text.startswith('@'):
        return text[1:]

    # Просто username
    if re.match(r'^[a-zA-Z]\w{3,}$', text):
        return text

    return None


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """/start — приветствие."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return
    await message.answer("Video Clipper Bot v0.1.0 | /help для списка команд")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """/help — список команд."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return
    await message.answer(
        "/sources — список каналов-источников\n"
        "/add_source <ID|URL|@username> — добавить источник\n"
        "/remove_source <ID> — удалить источник\n"
        "/status — статус системы"
    )


@router.message(Command("sources"))
async def cmd_sources(message: Message) -> None:
    """/sources — список активных каналов-источников."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return

    sources = await _db.get_active_sources()
    if not sources:
        await message.answer("Нет активных источников.")
        return

    lines = []
    for i, s in enumerate(sources, 1):
        title = s.get("chat_title") or s.get("chat_username") or str(s["chat_id"])
        count = s.get("video_count", 0)
        lines.append(f"{i}. <b>{title}</b> (<code>{s['chat_id']}</code>) — {count} видео")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("add_source"))
async def cmd_add_source(message: Message) -> None:
    """/add_source — добавить канал-источник."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return

    chat_id = None
    chat_title = None
    chat_username = None

    # Вариант 1: пересланное сообщение из канала
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        chat_title = message.forward_from_chat.title or "Неизвестный канал"
        chat_username = getattr(message.forward_from_chat, "username", None)

    else:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer(
                "📝 <b>Добавление источника</b>\n\n"
                "<b>Способ 1:</b> По ID\n"
                "<code>/add_source -1001234567890</code>\n\n"
                "<b>Способ 2:</b> По ссылке\n"
                "<code>/add_source https://t.me/channel_name</code>\n\n"
                "<b>Способ 3:</b> По username\n"
                "<code>/add_source @channel_name</code>\n\n"
                "<b>Способ 4:</b> Переслать любое сообщение из канала боту",
                parse_mode="HTML",
            )
            return

        input_value = args[1].strip()

        # Попытка распарсить как int (chat_id)
        try:
            chat_id = int(input_value)
        except ValueError:
            # Попробовать как ссылку/username
            username = _parse_telegram_link(input_value)
            if not username:
                await message.answer(
                    "❌ Неверный формат.\n\n"
                    "Поддерживаются: ID, https://t.me/channel, @username, username"
                )
                return

            # Получить entity через Telethon
            try:
                entity = await _tg_client.get_entity(username)
                chat_id = getattr(entity, "id", None)
                if chat_id is None:
                    raise ValueError("Не удалось получить ID канала")
                # Нормализовать к полному peer_id для каналов (-100...)
                if not str(chat_id).startswith("-100"):
                    chat_id = int(f"-100{chat_id}")
                chat_title = getattr(entity, "title", None) or username
                chat_username = getattr(entity, "username", None)
            except Exception as e:
                logger.error(f"Ошибка получения канала по username '{username}': {e}")
                await message.answer(
                    f"❌ Не удалось найти канал: <code>{username}</code>\n"
                    "Убедитесь, что userbot подписан на канал.",
                    parse_mode="HTML",
                )
                return

        # Если получили chat_id числом — получить название через Telethon
        if chat_title is None and chat_id is not None:
            try:
                entity = await _tg_client.get_entity(chat_id)
                chat_title = getattr(entity, "title", None) or str(chat_id)
                chat_username = getattr(entity, "username", None)
            except Exception as e:
                logger.warning(f"Не удалось получить название для {chat_id}: {e}")
                chat_title = str(chat_id)

    if chat_id is None:
        await message.answer("❌ Не удалось определить ID канала.")
        return

    await _db.add_source(chat_id, chat_title, chat_username)
    logger.info(f"Source added: {chat_title} ({chat_id}). Restart to apply monitor.")
    await message.answer(
        f"✅ Источник добавлен: <b>{chat_title}</b> (<code>{chat_id}</code>)\n"
        "ℹ️ Перезапустите бот для применения изменений.",
        parse_mode="HTML",
    )


@router.message(Command("remove_source"))
async def cmd_remove_source(message: Message) -> None:
    """/remove_source <chat_id> — удалить источник."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /remove_source <chat_id>")
        return

    try:
        chat_id = int(args[1].strip())
    except ValueError:
        await message.answer("❌ chat_id должен быть числом.")
        return

    removed = await _db.remove_source(chat_id)
    if removed:
        await message.answer(f"✅ Источник <code>{chat_id}</code> удалён.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Источник <code>{chat_id}</code> не найден.", parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """/status — статус системы."""
    if not _is_admin(message):
        await message.answer("Нет доступа")
        return

    sources = await _db.get_active_sources()
    video_counts = await _db.get_video_counts_by_status()
    pending_jobs = await _db.get_pending_jobs_count()

    lines = [
        f"📡 Активных источников: <b>{len(sources)}</b>",
        "",
        "🎬 Видео по статусам:",
    ]
    if video_counts:
        for status, count in sorted(video_counts.items()):
            lines.append(f"  • {status}: {count}")
    else:
        lines.append("  — нет видео")

    lines += [
        "",
        f"⚙️ Задач в очереди: <b>{pending_jobs}</b>",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML")
