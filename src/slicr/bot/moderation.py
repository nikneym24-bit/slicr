"""Обработчики модерации: Approve/Reject inline-кнопки."""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from slicr.constants import VideoStatus, JobType
from slicr.database import Database

logger = logging.getLogger(__name__)

router = Router()

# Модуль-уровень переменные (устанавливаются через setup())
_db: Database | None = None
_admin_id: int = 0


def setup(db: Database, admin_id: int) -> None:
    """Инициализация модуля с зависимостями (DI)."""
    global _db, _admin_id
    _db = db
    _admin_id = admin_id


@router.callback_query(lambda c: c.data and c.data.startswith("approve:"))
async def handle_approve(callback: CallbackQuery) -> None:
    """Обработчик кнопки Approve."""
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    video_id = int(callback.data.split(":")[1])

    await _db.update_video_status(video_id, VideoStatus.APPROVED)
    await _db.add_job(job_type=JobType.DOWNLOAD, video_id=video_id)

    await callback.message.edit_text(
        f"✅ Approved by admin | video #{video_id}",
        reply_markup=None,
    )
    await callback.answer("Approved")
    logger.info(f"Video {video_id} approved")


@router.callback_query(lambda c: c.data and c.data.startswith("reject:"))
async def handle_reject(callback: CallbackQuery) -> None:
    """Обработчик кнопки Reject."""
    if callback.from_user.id != _admin_id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    video_id = int(callback.data.split(":")[1])

    await _db.update_video_status(video_id, VideoStatus.REJECTED)

    await callback.message.edit_text(
        f"❌ Rejected by admin | video #{video_id}",
        reply_markup=None,
    )
    await callback.answer("Rejected")
    logger.info(f"Video {video_id} rejected")
