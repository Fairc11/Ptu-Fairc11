from __future__ import annotations
import enum
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel, Field


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class MediaType(str, enum.Enum):
    IMAGE_SET = "image_set"          # 图集/笔记
    VIDEO = "video"                  # 普通视频
    LIVE_PHOTO = "live_photo"        # 实况照片
    COMPREHENSIVE = "comprehensive"  # 混合内容（既有图片又有实况）


class TransitionType(str, enum.Enum):
    NONE = "none"
    FADE = "fade"
    KEN_BURNS = "ken_burns"


class LivePhotoSource(BaseModel):
    image_url: str
    video_url: str


class ScrapeResult(BaseModel):
    title: str = ""
    author: str = ""
    author_uid: str = ""
    media_type: MediaType
    image_urls: list[str] = []
    music_url: str | None = None
    music_title: str = ""
    cover_url: str | None = None
    live_photo_data: list[LivePhotoSource] = []
    aweme_id: str = ""
    raw_data: dict | None = None


class DownloadProgress(BaseModel):
    task_id: str
    stage: str          # resolving | downloading_images | downloading_music | processing | complete | error
    progress: float     # 0.0 ~ 1.0
    message: str = ""
    current_item: int = 0
    total_items: int = 0


class RenderOptions(BaseModel):
    image_duration: float = 3.0      # 每张图片显示秒数
    transition: TransitionType = TransitionType.FADE
    resolution: str = "1920x1080"
    fps: int = 30
    use_original_music: bool = True
    music_file: str | None = None    # 自定义音乐文件路径
    live_photo_mode: str = "image"   # image | video | both
    transition_duration: float = 0.7


class TaskInfo(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    share_url: str
    status: TaskStatus = TaskStatus.PENDING
    metadata: ScrapeResult | None = None
    download_path: str | None = None
    output_path: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ScrapeRequest(BaseModel):
    url: str


class ScrapeResponse(BaseModel):
    task_id: str
    metadata: ScrapeResult


class RenderRequest(BaseModel):
    options: RenderOptions = RenderOptions()
