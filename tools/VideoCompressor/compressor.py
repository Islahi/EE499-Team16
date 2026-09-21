"""Safe FFmpeg command construction and local media processing."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_INPUTS = {".mp4", ".avi", ".mov", ".mkv", ".m4a", ".wav", ".mp3", ".webm"}
VIDEO_INPUTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


@dataclass(frozen=True)
class CompressionResult:
    output_path: Path
    input_bytes: int
    output_bytes: int

    @property
    def reduction_percent(self) -> float:
        if self.input_bytes <= 0:
            return 0.0
        return 100.0 * (1.0 - self.output_bytes / self.input_bytes)


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def validate_input(path: Path, require_video: bool = False) -> None:
    if not path.is_file():
        raise ValueError(f"Input file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_INPUTS:
        raise ValueError(f"Unsupported input format: {suffix or '(none)'}")
    if require_video and suffix not in VIDEO_INPUTS:
        raise ValueError("Video compression requires a video input file.")


def unique_output_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def build_audio_command(ffmpeg: str, input_path: Path, output_path: Path, bitrate_kbps: int) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        f"{bitrate_kbps}k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def build_video_command(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    crf: int,
    preset: str,
    audio_bitrate_kbps: int,
    height: int | None,
    fps: int | None,
) -> list[str]:
    filters: list[str] = []
    if height is not None:
        filters.append(f"scale=-2:{height}")
    if fps is not None:
        filters.append(f"fps={fps}")

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
    ]
    if filters:
        command.extend(["-vf", ",".join(filters)])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate_kbps}k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def run_ffmpeg(command: list[str], input_path: Path, output_path: Path) -> CompressionResult:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        output_path.unlink(missing_ok=True)
        detail = completed.stderr.strip() or "FFmpeg returned an unknown error."
        raise RuntimeError(detail)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg completed without producing a valid output file.")
    return CompressionResult(
        output_path=output_path,
        input_bytes=input_path.stat().st_size,
        output_bytes=output_path.stat().st_size,
    )
