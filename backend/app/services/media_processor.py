"""
Media processor.

Builds and executes FFmpeg commands to create slideshow videos
from images with background music and transitions.
"""
from __future__ import annotations
import subprocess
import asyncio
import math
import logging
import sys
from pathlib import Path
from typing import Optional
from ..models.schemas import RenderOptions, TransitionType
from ..config import settings
from .progress import progress_emitter


class MediaProcessor:
    """FFmpeg-based slideshow video generator."""

    def __init__(self):
        self.ffmpeg = settings.ffmpeg_path
        self.last_render_metadata: dict = {}

    @staticmethod
    def _subprocess_kwargs() -> dict:
        kwargs = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return kwargs

    def _run_media_command(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, timeout=timeout, **self._subprocess_kwargs())

    @staticmethod
    def _choose_output_path(output_dir: Path) -> Path:
        output_path = output_dir / "douyin_slideshow.mp4"
        if not output_path.exists():
            return output_path
        try:
            with output_path.open("ab"):
                pass
            return output_path
        except OSError:
            counter = 1
            while True:
                candidate = output_dir / f"douyin_slideshow_{counter}.mp4"
                if not candidate.exists():
                    return candidate
                counter += 1

    async def render_slideshow(
        self,
        task_id: str,
        image_paths: list[str],
        music_path: Optional[str],
        options: RenderOptions,
        output_dir: Path,
        live_photo_videos: Optional[list[str]] = None,
    ) -> str:
        """
        Create a slideshow video from images with background music.

        Returns the path to the rendered video.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._choose_output_path(output_dir)

        # Filter existing images and handle live photos
        valid_images = []
        for p in image_paths:
            if Path(p).exists():
                valid_images.append(p)

        valid_live_videos = [p for p in (live_photo_videos or []) if Path(p).exists()]
        if not valid_images and not valid_live_videos:
            raise ValueError("No valid images found to render")

        await progress_emitter.emit_stage(
            task_id, "processing", 0,
            f"准备渲染 {len(valid_images)} 张图片"
        )

        if music_path or valid_live_videos:
            cmd, render_meta = self._build_douyin_clean_command(
                valid_images or valid_live_videos,
                music_path,
                options,
                str(output_path),
                live_photo_videos=valid_live_videos,
            )
            await progress_emitter.emit_stage(
                task_id, "processing", 0.15,
                f"排片完成：循环 {render_meta['cycle_count']} 次"
            )
        elif options.transition == TransitionType.KEN_BURNS:
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
            render_meta = {
                "music_duration_seconds": None,
                "cycle_count": 1,
                "scene_count": len(valid_images),
                "rendered_scene_count": len(valid_images),
            }

        self.last_render_metadata = {
            **render_meta,
            "output_path": str(output_path),
            "output_filename": output_path.name,
            "ffmpeg_path": self.ffmpeg,
            "visual_count": len(valid_images),
            "live_video_count": len(valid_live_videos),
            "resolution": options.resolution,
            "fps": options.fps,
        }
        logging.getLogger("app.media").info(
            "渲染排片: task=%s FFmpeg=%s 素材=%s 实况视频=%s 音乐=%s 循环=%s 输出=%s",
            task_id,
            self.ffmpeg,
            len(valid_images),
            len(valid_live_videos),
            (
                f"{self.last_render_metadata['music_duration_seconds']:.3f}s"
                if self.last_render_metadata.get("music_duration_seconds")
                else "无"
            ),
            self.last_render_metadata["cycle_count"],
            output_path,
        )

        await progress_emitter.emit_stage(
            task_id, "processing", 0.3,
            f"正在渲染视频..."
        )

        # Execute FFmpeg (use run_in_executor for Windows compatibility)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._run_media_command(cmd, timeout=300)
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
        logging.getLogger("app.media").info(
            "渲染完成: task=%s 输出=%s", task_id, output_path
        )

        return str(output_path)

    def _get_scale_filter(self, resolution: str, *, fit: str = "cover") -> str:
        """Get FFmpeg scale/pad filter string for given resolution."""
        w, h = resolution.split("x")
        if fit == "contain":
            return (
                f"scale=w='min({w},iw)':h='min({h},ih)':"
                f"force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2:flags=lanczos,"
            f"crop={w}:{h}"
        )

    def _probe_duration(self, path: str) -> float | None:
        """Probe media duration in seconds using ffprobe."""
        ffprobe = "ffprobe"
        ffmpeg_path = Path(self.ffmpeg)
        if ffmpeg_path.name:
            candidate = ffmpeg_path.with_name("ffprobe.exe")
            if candidate.exists():
                ffprobe = str(candidate)
        result = self._run_media_command(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            timeout=30,
        )
        if result.returncode != 0:
            return None
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            return None
        return duration if duration > 0 else None

    def _build_douyin_clean_command(
        self,
        visual_paths: list[str],
        music: Optional[str],
        options: RenderOptions,
        output: str,
        live_photo_videos: Optional[list[str]] = None,
    ) -> tuple[list[str], dict]:
        """Build a clean vertical Douyin-style render command."""
        import os as _os

        duration = max(float(options.image_duration or 2.6), 0.1)
        transition_duration = min(max(float(options.transition_duration or 0.28), 0.0), duration / 2)
        visuals = [p for p in visual_paths if Path(p).exists()]
        videos = [p for p in (live_photo_videos or []) if Path(p).exists()]
        scene_count = max(len(visuals), len(videos))
        if scene_count < 1:
            raise ValueError("No valid visual media found to render")

        has_music = bool(music and Path(music).exists())
        music_duration = self._probe_duration(music) if has_music else None
        cycle_duration = scene_count * duration
        cycle_count = 1
        single_visual_scene = scene_count == 1
        if music_duration and not single_visual_scene:
            cycle_count = max(1, math.ceil(music_duration / cycle_duration))

        scenes: list[tuple[str, bool]] = []
        if single_visual_scene:
            if videos:
                scenes.append((videos[0], True))
            else:
                scenes.append((visuals[0], False))
        else:
            for _ in range(cycle_count):
                for i in range(scene_count):
                    if i < len(videos):
                        scenes.append((videos[i], True))
                    else:
                        scenes.append((visuals[i % len(visuals)], False))

        cmd = [self.ffmpeg, "-y"]
        for path, is_video in scenes:
            input_duration = (music_duration or duration) if single_visual_scene else (duration + transition_duration)
            if is_video:
                cmd.extend([
                    "-stream_loop", "-1", "-t",
                    f"{input_duration:.3f}", "-i", _os.path.abspath(path),
                ])
            else:
                cmd.extend([
                    "-loop", "1", "-t",
                    f"{input_duration:.3f}", "-i", _os.path.abspath(path),
                ])
        if has_music:
            cmd.extend(["-i", _os.path.abspath(music)])

        scale_filter = self._get_scale_filter(
            options.resolution,
            fit="contain" if single_visual_scene and videos else "cover",
        )
        parts = [
            f"[{i}:v]{scale_filter},setsar=1,fps={options.fps},format=yuv420p,setpts=PTS-STARTPTS[v{i}]"
            for i in range(len(scenes))
        ]
        if len(scenes) > 1 and transition_duration > 0:
            previous = "v0"
            for i in range(1, len(scenes)):
                out_label = "vout" if i == len(scenes) - 1 else f"vx{i}"
                offset = max(i * duration, 0.01)
                parts.append(
                    f"[{previous}][v{i}]xfade=transition=wipeleft:"
                    f"duration={transition_duration:.3f}:offset={offset:.3f}[{out_label}]"
                )
                previous = out_label
        else:
            concat_inputs = "".join(f"[v{i}]" for i in range(len(scenes)))
            parts.append(f"{concat_inputs}concat=n={len(scenes)}:v=1:a=0[vout]")
        cmd.extend(["-filter_complex", ";".join(parts), "-map", "[vout]"])

        if has_music:
            cmd.extend(["-map", f"{len(scenes)}:a:0", "-c:a", "aac", "-b:a", "192k"])
            if music_duration:
                cmd.extend(["-t", f"{music_duration:.3f}"])
            else:
                cmd.extend(["-shortest"])
        else:
            cmd.extend(["-an"])

        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"])
        cmd.append(_os.path.abspath(output))
        return cmd, {
            "music_duration_seconds": music_duration,
            "cycle_count": cycle_count,
            "scene_count": scene_count,
            "rendered_scene_count": len(scenes),
            "transition": "wipeleft" if len(scenes) > 1 and transition_duration > 0 else "none",
            "transition_duration_seconds": transition_duration,
        }

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

    def _build_live_photo_command(
        self, images: list[str], videos: list[str],
        music: Optional[str], options: RenderOptions, output: str
    ) -> list[str]:
        """Live photo synthesis: combine image+video pairs with music."""
        import os as _os
        import tempfile
        cmd = [self.ffmpeg, "-y"]
        has_music = music and Path(music).exists()

        # Each live photo: video first, then still image as overlay
        n = min(len(images), len(videos))
        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        lines = []
        for i in range(n):
            vid_path = _os.path.abspath(videos[i])
            lines.append(f"file '{vid_path}'")
            # Show video for its duration (ffprobe not needed, use file duration)
            # Then show still image for the remaining image_duration
            img_path = _os.path.abspath(images[i])
            lines.append(f"file '{img_path}'")
            lines.append(f"duration {options.image_duration}")
        # Handle remaining images without video (COMPREHENSIVE type)
        for i in range(n, len(images)):
            img_path = _os.path.abspath(images[i])
            lines.append(f"file '{img_path}'")
            lines.append(f"duration {options.image_duration}")

        if lines:
            concat_file.write("\n".join(lines))
            concat_file.close()
            cmd.extend(["-f", "concat", "-safe", "0", "-i", concat_file.name])

        # Add music if available
        if has_music:
            cmd.extend(["-i", _os.path.abspath(music)])

        # Scale and encode
        res = options.resolution
        w, h = res.split("x")
        cmd.extend([
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p",
        ])
        if has_music:
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            cmd.extend(["-an"])
        cmd.append(output)
        return cmd


media_processor = MediaProcessor()
