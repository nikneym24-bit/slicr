"""
Глобальное состояние веб-приложения.

Хранит конфиг, очередь задач, активные процессы.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from slicr.config import Config
from slicr.services.processor import ProcessingOptions, ProcessingResult, VideoProcessor

logger = logging.getLogger(__name__)


class WebSocketLogHandler(logging.Handler):
    """Logging handler — транслирует ВСЕ логи приложения в WebSocket и терминал."""

    def __init__(self, state: "AppState") -> None:
        super().__init__()
        self._state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            msg = f"[{ts}] {record.levelname} {record.name} — {record.getMessage()}"
            self._state._broadcast_log(msg)
            # Дублируем в терминал (print гарантированно работает на Windows)
            print(msg, flush=True)
        except Exception:
            pass

# Директории
UPLOAD_DIR = os.path.join("storage", "uploads")
OUTPUT_DIR = os.path.join("storage", "clips")


class TaskStatus(StrEnum):
    """Статус задачи обработки."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingTask:
    """Задача обработки видео."""
    task_id: str
    filename: str
    input_path: str
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0
    message: str = ""
    result: ProcessingResult | None = None
    error: str = ""
    clips: list[str] = field(default_factory=list)


class AppState:
    """Состояние приложения — единый владелец задач и ресурсов."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.tasks: dict[str, ProcessingTask] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._log_subscribers: list[asyncio.Queue[str]] = []

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Подключаем трансляцию ВСЕХ логов в WebSocket
        self._log_handler = WebSocketLogHandler(self)
        self._log_handler.setLevel(logging.INFO)
        logging.getLogger("slicr").addHandler(self._log_handler)

        # Запускаем воркер обработки
        self._worker_task = asyncio.get_event_loop().create_task(self._worker())

    async def shutdown(self) -> None:
        """Остановить воркер."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    def subscribe_logs(self) -> asyncio.Queue[str]:
        """Подписаться на лог-стрим (для WebSocket)."""
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._log_subscribers.append(q)
        return q

    def unsubscribe_logs(self, q: asyncio.Queue[str]) -> None:
        """Отписаться от лог-стрима."""
        if q in self._log_subscribers:
            self._log_subscribers.remove(q)

    def _broadcast_log(self, msg: str) -> None:
        """Отправить сообщение всем подписчикам."""
        for q in self._log_subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def create_task(
        self,
        filename: str,
        input_path: str,
        options: ProcessingOptions,
    ) -> ProcessingTask:
        """Создать задачу обработки и поставить в очередь."""
        task_id = uuid.uuid4().hex[:8]
        task = ProcessingTask(
            task_id=task_id,
            filename=filename,
            input_path=input_path,
        )
        task._options = options  # type: ignore[attr-defined]
        self.tasks[task_id] = task
        self._queue.put_nowait(task_id)
        self._broadcast_log(f"[{task_id}] В очереди: {filename}")
        logger.info("Задача %s создана: %s", task_id, filename)
        return task

    async def _worker(self) -> None:
        """Фоновый воркер — обрабатывает по одной задаче."""
        logger.info("Воркер обработки запущен")
        while True:
            task_id = await self._queue.get()
            task = self.tasks.get(task_id)
            if not task:
                continue

            task.status = TaskStatus.PROCESSING
            task.message = "Начинаем обработку..."
            self._broadcast_log(f"[{task_id}] Обработка: {task.filename}")

            processor = VideoProcessor(self.config)
            try:
                options: ProcessingOptions = task._options  # type: ignore[attr-defined]

                def on_progress(pct: float, msg: str) -> None:
                    task.progress = pct
                    task.message = msg
                    self._broadcast_log(f"[{task_id}] {pct:.0%} {msg}")

                result = await processor.process(
                    input_path=task.input_path,
                    output_dir=OUTPUT_DIR,
                    options=options,
                    on_progress=on_progress,
                )

                task.result = result
                task.clips = [clip.final_path for clip in result.clips]
                task.status = TaskStatus.COMPLETED
                task.progress = 1.0
                task.message = f"Готово! Клипов: {len(result.clips)}"
                self._broadcast_log(
                    f"[{task_id}] Готово: {len(result.clips)} клипов"
                )
                logger.info("Задача %s завершена: %d клипов", task_id, len(result.clips))

            except Exception as e:
                task.status = TaskStatus.FAILED
                error_msg = str(e) or repr(e)
                task.error = error_msg
                task.message = f"Ошибка: {error_msg}"
                self._broadcast_log(f"[{task_id}] ОШИБКА: {error_msg}")
                logger.error("Задача %s провалена: %s", task_id, e, exc_info=True)

            finally:
                await processor.close()
