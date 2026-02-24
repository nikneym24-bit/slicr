"""Клавиатуры Telegram-бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_moderation_keyboard(video_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура модерации: Approve / Reject.

    Callback data format:
      - "approve:{video_id}"
      - "reject:{video_id}"
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve:{video_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject:{video_id}"),
        ]
    ])


def format_video_info(video: dict) -> str:
    """
    Форматировать инфо о видео для отправки в Tech канал.

    Формат:
      📹 Канал: {chat_id}
      ⏱ {duration}с | 📦 {size_mb}MB
      🆔 video #{video_id}
    """
    duration = video.get("duration", 0)
    size_bytes = video.get("file_size", 0)
    size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else 0
    chat_id = video.get("source_chat_id", "?")
    video_id = video.get("id", "?")

    return (
        f"📹 Канал: <code>{chat_id}</code>\n"
        f"⏱ {duration}с | 📦 {size_mb}MB\n"
        f"🆔 video #{video_id}"
    )
