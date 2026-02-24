from enum import StrEnum


class VideoStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    SELECTING = "selecting"
    SELECTED = "selected"
    PROCESSING = "processing"
    READY = "ready"
    MODERATION = "moderation"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobType(StrEnum):
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    SELECT = "select"
    EDIT = "edit"
    PUBLISH = "publish"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Platform(StrEnum):
    VK_CLIPS = "vk_clips"
    TELEGRAM = "telegram"
