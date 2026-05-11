"""
Media processor.

Builds and executes FFmpeg commands to create slideshow videos
from images with background music and transitions.
"""
from __future__ import annotations
import subprocess
import asyncio
from pathlib import Path
from typing import Optional
from ..models.schemas import RenderOptions, TransitionType
from ..config import settings
from .progress import progress_emitter


class MediaProcessor:
    """FFmpeg-based slideshow video generator."""

    def __init__(self):
        self.ffmpeg = settings.ffmpeg_path

    async def render_slideshow(
        self,
        task_id: str,
        image_paths: list[str],
        music_path: Optional[str],
        options: RenderOptions,
        output_dir: Path,
    ) -> str:
        """
        Create a slideshow video from images with background music.

        Returns the path to the rendered video.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "slideshow.mp4"

        # Filter existing images and handle live photos
        valid_images = []
        for p in image_paths:
            if Path(p).exists():
                valid_images.append(p)

        if not valid_images:
            raise ValueError("No valid images found to render")

        await progress_emitter.emit_stage(
            task_id, "processing", 0,
            f"准备渲染 {len(valid_images)} 张图片"
        )

        # Build and execute FFmpeg command based on transition type
        if options.transition == TransitionType.KEN_BURNS:
            cmd = self._build_kenburns_command(
                valid_images, music_path, options, str(output_path)
            )
        elif options.transition == TransitionType.FADE and len(valid_images) > 1:
            cmd = self._build_xfade_command(
                valid_images, music_path, options, str(output_path)
            )
        else:
            cmd = self._build_simple_command(
                valid_images, music_path, options, str(output_path)
            )

        await progress_emitter.emit_stage(
            task_id, "processing", 0.3,
            f"正在渲染视频..."
        )

        # Execute FFmpeg (use run_in_executor for Windows compatibility)
        import subprocess as sp

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: sp.run(cmd, capture_output=True, text=True, timeout=300)
        )

        if result.returncode != 0:
            # Real error is at end of stderr (version info is at the start)
            if result.stderr:
                lines = result.stderr.split("\n")
                error_lines = [l for l in lines if "Error" in l or "error" in l or "No such" in l]
                error_msg = "; ".join(error_lines[-3:]) if error_lines else lines[-1]
            else:
                error_msg = "Unknown error"
            raise RuntimeError(f"FFmpeg failed: {error_msg}")

        await progress_emitter.emit_stage(
            task_id, "processing", 1.0,
            "渲染完成！"
        )

        return str(output_path)

    def _get_scale_filter(self, resolution: str) -> str:
        """Get FFmpeg scale/pad filter string for given resolution."""
        w, h = resolution.split("x")
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}"
        )

    def _build_simple_command(
        self, images: list[str], music: Optional[str],
        options: RenderOptions, output: str
    ) -> list[str]:
        """Simple slideshow: each image shown for N seconds using -loop 1 inputs."""
        import os as _os
        cmd = [self.ffmpeg, "-y"]
        duration = options.image_duration
        n = len(images)

        # Each image as a separate -loop 1 input
        for img in images:
            cmd.extend(["-loop", "1", "-t", str(duration), "-i", _os.path.abspath(img)])

        # Music
        has_music = music and Path(music).exists()
        if has_music:
            cmd.extend(["-i", _os.path.abspath(music)])

        # Build concat filter
        resolution = options.resolution
        scale_filter = self._get_scale_filter(resolution)
        parts = []
        for i in range(n):
            parts.append(f"[{i}:v]{scale_filter},setpts=PTS-STARTPTS[v{i}]")
        concat_in = "".join(f"[v{i}]" for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")
        cmd.extend(["-filter_complex", ";".join(parts)])
        cmd.extend(["-map", "[vout]", "-pix_fmt", "yuv420p"])
        if has_music:
            cmd.extend(["-map", f"{n}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            cmd.extend(["-an"])
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "22"])
        cmd.append(_os.path.abspath(output))
        return cmd

    def _build_xfade_command(
        self, images: list[str], music: Optional[str],
        options: RenderOptions, output: str
    ) -> list[str]:
        """Slideshow with crossfade transitions using xfade filter."""
        cmd = [self.ffmpeg, "-y"]
        duration = options.image_duration
        trans_dur = options.transition_duration
        resolution = options.resolution
        n = len(images)

        # Each image as a loop input (use absolute paths)
        import os as _os
        for img in images:
            cmd.extend(["-loop", "1", "-t", str(duration + trans_dur), "-i", _os.path.abspath(img)])

        # Music input (absolute path)
        import os as _os
        has_music = music and Path(music).exists()
        if has_music:
            cmd.extend(["-i", _os.path.abspath(music)])

        # Build filter complex string
        scale_filter = self._get_scale_filter(resolution)
        parts = []

        for i in range(n):
            parts.append(
                f"[{i}:v]{scale_filter},setpts=PTS-STARTPTS[v{i}]"
            )

        # Chain xfade transitions
        for i in range(n - 1):
            offset = i * duration
            if i == 0:
                parts.append(
                    f"[v{i}][v{i+1}]xfade=transition=fade:duration={trans_dur}:offset={offset}[vf{i}]"
                )
            else:
                parts.append(
                    f"[vf{i-1}][v{i+1}]xfade=transition=fade:duration={trans_dur}:offset={offset}[vf{i}]"
                )

        last = f"vf{n-2}" if n > 1 else "v0"
        filter_str = ";".join(parts)

        cmd.extend(["-filter_complex", filter_str])
        cmd.extend(["-map", f"[{last}]"])

        if has_music:
            cmd.extend(["-map", f"{n}:a"])
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            cmd.extend(["-an"])

        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "22"])
        cmd.append(output)
        return cmd

    def _build_kenburns_command(
        self, images: list[str], music: Optional[str],
        options: RenderOptions, output: str
    ) -> list[str]:
        """Slideshow with Ken Burns zoom effect."""
        import tempfile
        cmd = [self.ffmpeg, "-y"]
        resolution = options.resolution

        # Create concat file for the image sequence
        concat_lines = []
        for img in images:
            concat_lines.append(f"file '{img}'")
            concat_lines.append(f"duration {options.image_duration}")
        if images:
            concat_lines.append(f"file '{images[-1]}'")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            f.write("\n".join(concat_lines))
            concat_file = f.name

        cmd.extend(["-f", "concat", "-safe", "0", "-i", concat_file])

        # Music input (absolute path)
        import os as _os
        has_music = music and Path(music).exists()
        if has_music:
            cmd.extend(["-i", _os.path.abspath(music)])

        # Ken Burns effect with zoompan
        fps = options.fps
        total_duration = len(images) * options.image_duration
        total_frames = int(total_duration * fps)

        zoompan_filter = (
            f"zoompan=z='if(lte(zoom,1.0),1.3,zoom+0.002)':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={fps * 5}:s={resolution.replace('x', ':')},"
            f"trim=start_frame=0:end_frame={total_frames},"
            f"setpts=N/FRAME_RATE/TB,"
            f"fps={fps},format=yuv420p"
        )
        cmd.extend(["-vf", zoompan_filter])
        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "20"])

        if has_music:
            cmd.extend(["-map", "1:a"])
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            cmd.extend(["-an"])

        cmd.append(output)
        return cmd


media_processor = MediaProcessor()
