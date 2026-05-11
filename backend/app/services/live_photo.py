"""
Live Photo handler.

Handles detection and processing of iPhone Live Photos (实况照片).
These consist of a still image (.heic or .jpg) + a short video (.mov).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from ..models.schemas import LivePhotoSource


class LivePhotoProcessor:
    """Process live photos: HEIC conversion, video extraction."""

    @staticmethod
    def convert_heic_to_jpeg(heic_path: str, output_dir: Optional[Path] = None) -> str:
        """Convert HEIC image to JPEG using pillow-heif."""
        try:
            import pillow_heif
            from PIL import Image
        except ImportError:
            raise RuntimeError("pillow-heif not installed. Run: pip install pillow-heif pillow")

        pillow_heif.register_heif_opener()
        src = Path(heic_path)
        dst_dir = output_dir or src.parent
        dst_path = dst_dir / f"{src.stem}.jpg"

        if dst_path.exists():
            return str(dst_path)

        img = Image.open(src)
        img.convert("RGB").save(dst_path, "JPEG", quality=95)
        return str(dst_path)

    @staticmethod
    def is_heic(image_path: str) -> bool:
        """Check if file is HEIC format."""
        return Path(image_path).suffix.lower() in (".heic", ".heif")

    @staticmethod
    def extract_frame_from_video(video_path: str, output_dir: Optional[Path] = None,
                                 ffmpeg_path: str = "ffmpeg") -> str:
        """Extract a single frame from a live photo video."""
        import subprocess
        src = Path(video_path)
        dst_dir = output_dir or src.parent
        dst_path = dst_dir / f"{src.stem}_frame.jpg"

        if dst_path.exists():
            return str(dst_path)

        subprocess.run(
            [ffmpeg_path, "-i", video_path, "-vframes", "1", str(dst_path)],
            capture_output=True, check=True
        )
        return str(dst_path)

    @staticmethod
    def ensure_jpeg(image_path: str, output_dir: Optional[Path] = None) -> str:
        """Convert to JPEG if HEIC, otherwise return original path."""
        if LivePhotoProcessor.is_heic(image_path):
            return LivePhotoProcessor.convert_heic_to_jpeg(image_path, output_dir)
        return image_path


live_photo_processor = LivePhotoProcessor()
