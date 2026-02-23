import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from video_clipper.config import load_config
from video_clipper.database import Database
from video_clipper.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════╗
║        VIDEO CLIPPER v0.1.0          ║
║   Telegram → Clips → VK / Telegram  ║
╚══════════════════════════════════════╝
"""


async def main():
    # 1. Загрузить конфиг
    config = load_config()

    # 2. Настроить логирование
    setup_logging()

    # 3. Показать баннер
    print(BANNER)
    logger.info("Starting Video Clipper...")

    # 4. Показать режим
    if config.dev_mode:
        logger.info("MODE: Development")
        logger.info(f"  Mock GPU:      {config.mock_gpu}")
        logger.info(f"  Mock Selector: {config.mock_selector}")
        logger.info(f"  Mock Monitor:  {config.mock_monitor}")
    else:
        logger.info("MODE: Production")

    # 5. Инициализировать БД
    db = Database(config.db_path)
    await db.init_tables()
    logger.info(f"Database ready: {config.db_path}")

    # 6. Инициализировать Telegram-клиент (Telethon)
    from video_clipper.services.telegram_client import TelegramClientWrapper

    tg_client = TelegramClientWrapper(config)

    if not config.mock_monitor:
        await tg_client.connect()
        logger.info("Telegram client connected")
    else:
        logger.info("Telegram client: MOCK mode (skipped)")

    # 7. Инициализировать aiogram Bot + Dispatcher
    from video_clipper.bot.keyboards import get_moderation_keyboard, format_video_info
    from video_clipper.bot import moderation, handlers

    aiogram_bot = None
    dp = None

    if not config.mock_monitor and config.bot_token:
        aiogram_bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        dp = Dispatcher()

        # DI: инициализировать модули с зависимостями
        moderation.setup(db, config.admin_id)
        handlers.setup(db, tg_client, config.admin_id)

        # Подключить роутеры
        dp.include_router(handlers.router)
        dp.include_router(moderation.router)

        logger.info("Aiogram bot initialized")

    # 8. Callback: Monitor переслал видео → отправить кнопки модерации в Tech
    async def on_new_video(video_id: int) -> None:
        """Monitor переслал видео → отправить инфо + кнопки в Tech канал."""
        if aiogram_bot is None:
            return
        video = await db.get_video(video_id)
        if video is None:
            return
        keyboard = get_moderation_keyboard(video_id)
        info_text = format_video_info(video)
        await aiogram_bot.send_message(
            config.tech_channel_id,
            info_text,
            reply_markup=keyboard,
        )
        logger.debug(f"Moderation keyboard sent for video {video_id}")

    # 9. Инициализировать Monitor с callback
    from video_clipper.pipeline.monitor import TelegramMonitor

    monitor = TelegramMonitor(config, db, tg_client, on_new_video=on_new_video)
    await monitor.start()

    # 10. Downloader (Stage 2c)
    from video_clipper.pipeline.downloader import VideoDownloader

    downloader = VideoDownloader(config, db, tg_client)
    await downloader.start()

    # Периодическая очистка старых файлов
    async def periodic_cleanup():
        """Периодическая очистка старых файлов."""
        while True:
            await asyncio.sleep(3600)  # каждый час
            try:
                await downloader.cleanup_old_files()
            except Exception as e:
                logger.error(f"Ошибка очистки: {e}")

    if config.cleanup_enabled and not config.mock_monitor:
        asyncio.create_task(periodic_cleanup())

    # Загрузить остальные заглушки (проверка что грузятся)
    from video_clipper.pipeline.orchestrator import PipelineOrchestrator
    from video_clipper.pipeline.transcriber import WhisperTranscriber
    from video_clipper.pipeline.selector import MomentSelector
    from video_clipper.pipeline.editor import VideoEditor
    from video_clipper.pipeline.publisher import ClipPublisher
    from video_clipper.gpu.guard import GPUGuard

    logger.info("All modules loaded. System ready.")

    # 11. Запуск
    try:
        if config.mock_monitor:
            await asyncio.Event().wait()
        elif dp and aiogram_bot:
            # Параллельно: Telethon (event handlers) + aiogram (long polling)
            async def run_telethon():
                await tg_client.client.run_until_disconnected()

            await asyncio.gather(
                dp.start_polling(
                    aiogram_bot,
                    allowed_updates=["message", "callback_query"],
                ),
                run_telethon(),
            )
        else:
            await tg_client.client.run_until_disconnected()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await downloader.stop()
        await monitor.stop()
        if not config.mock_monitor:
            await tg_client.disconnect()
        if aiogram_bot:
            await aiogram_bot.session.close()
        await db.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
