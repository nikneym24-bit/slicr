"""Telegram-бот: команды и модерация."""

from slicr.bot.handlers import router as handlers_router
from slicr.bot.moderation import router as moderation_router

__all__ = ["handlers_router", "moderation_router"]
