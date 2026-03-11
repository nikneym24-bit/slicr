"""
API-эндпоинты веб-сервиса.

POST /api/process     — загрузить видео и запустить обработку
GET  /api/tasks       — список всех задач
GET  /api/tasks/{id}  — статус конкретной задачи
GET  /api/download/{id}/{idx} — скачать готовый клип
GET  /api/health      — healthcheck
"""

import asyncio
import os
import logging

import aiofiles
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from slicr.services.processor import ProcessingOptions
from slicr.web.state import AppState, UPLOAD_DIR

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_state(request: Request) -> AppState:
    return request.app.state.app_state


@router.get("/health")
async def health() -> dict:
    """Healthcheck."""
    return {"status": "ok", "service": "slicr"}


@router.post("/process")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    crop_enabled: bool = Form(True),
    crop_x_offset: float = Form(0.5),
    subtitles_enabled: bool = Form(True),
    max_clip_duration: int = Form(60),
    min_clip_duration: int = Form(15),
) -> dict:
    """Загрузить видео и запустить обработку."""
    state = _get_state(request)

    # Сохраняем загруженный файл чанками (не грузим целиком в RAM)
    filename = file.filename or "video.mp4"
    input_path = os.path.join(UPLOAD_DIR, filename)
    total = 0
    async with aiofiles.open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            await f.write(chunk)
            total += len(chunk)

    logger.info("Загружен файл: %s (%.1f MB)", filename, total / 1024 / 1024)

    options = ProcessingOptions(
        crop_enabled=crop_enabled,
        crop_x_offset=crop_x_offset,
        subtitles_enabled=subtitles_enabled,
        max_clip_duration=max_clip_duration,
        min_clip_duration=min_clip_duration,
    )

    task = state.create_task(filename, input_path, options)
    return {"task_id": task.task_id, "status": task.status}


@router.post("/preview")
async def preview_frame(
    file: UploadFile = File(...),
) -> FileResponse:
    """Извлечь один кадр из видео для превью кропа."""
    filename = file.filename or "video.mp4"
    input_path = os.path.join(UPLOAD_DIR, filename)

    # Сохраняем файл если ещё нет
    if not os.path.exists(input_path):
        async with aiofiles.open(input_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                await f.write(chunk)
    else:
        await file.read()  # Читаем чтобы закрыть stream

    # Извлекаем кадр через ffmpeg
    frame_path = os.path.join(UPLOAD_DIR, f"_preview_{os.path.splitext(filename)[0]}.jpg")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-ss", "1", "-i", input_path,
        "-frames:v", "1", "-q:v", "2", frame_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if not os.path.exists(frame_path):
        return JSONResponse({"error": "Не удалось извлечь кадр"}, status_code=500)

    return FileResponse(frame_path, media_type="image/jpeg")


@router.get("/tasks")
async def list_tasks(request: Request) -> list[dict]:
    """Список всех задач."""
    state = _get_state(request)
    return [
        {
            "task_id": t.task_id,
            "filename": t.filename,
            "status": t.status,
            "progress": t.progress,
            "message": t.message,
            "clips_count": len(t.clips),
            "error": t.error,
        }
        for t in state.tasks.values()
    ]


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str) -> dict:
    """Статус конкретной задачи."""
    state = _get_state(request)
    task = state.tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "Задача не найдена"}, status_code=404)

    return {
        "task_id": task.task_id,
        "filename": task.filename,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "clips": [
            {"index": i, "path": os.path.basename(p)}
            for i, p in enumerate(task.clips)
        ],
        "error": task.error,
    }


@router.get("/download/{task_id}/{clip_index}")
async def download_clip(request: Request, task_id: str, clip_index: int) -> FileResponse:
    """Скачать готовый клип."""
    state = _get_state(request)
    task = state.tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "Задача не найдена"}, status_code=404)

    if clip_index < 0 or clip_index >= len(task.clips):
        return JSONResponse({"error": "Клип не найден"}, status_code=404)

    clip_path = task.clips[clip_index]
    if not os.path.exists(clip_path):
        return JSONResponse({"error": "Файл не найден"}, status_code=404)

    return FileResponse(
        clip_path,
        media_type="video/mp4",
        filename=os.path.basename(clip_path),
    )
