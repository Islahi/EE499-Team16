"""Local Streamlit interface for FFmpeg meeting-media compression."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from compressor import (
    build_audio_command,
    build_video_command,
    find_ffmpeg,
    run_ffmpeg,
    unique_output_path,
    validate_input,
)


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "05_Meetings" / "Raw_Recordings"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def process_file(
    input_path: Path,
    output_dir: Path,
    mode: str,
    audio_bitrate: int,
    crf: int,
    preset: str,
    height: int | None,
    fps: int | None,
):
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg was not found on PATH. Install FFmpeg and restart the terminal.")

    if mode == "Extract transcription audio":
        validate_input(input_path)
        output_path = unique_output_path(output_dir, f"{input_path.stem}_audio", ".m4a")
        command = build_audio_command(ffmpeg, input_path, output_path, audio_bitrate)
    else:
        validate_input(input_path, require_video=True)
        output_path = unique_output_path(output_dir, f"{input_path.stem}_compressed", ".mp4")
        command = build_video_command(
            ffmpeg,
            input_path,
            output_path,
            crf,
            preset,
            audio_bitrate,
            height,
            fps,
        )
    return run_ffmpeg(command, input_path, output_path)


st.set_page_config(page_title="Meeting media compressor", page_icon=":material/compress:", layout="centered")
st.title("Meeting media compressor")
st.caption("Compress recordings locally with FFmpeg. No recording is uploaded to an external service.")

ffmpeg_path = find_ffmpeg()
if ffmpeg_path:
    st.success(f"FFmpeg detected: `{ffmpeg_path}`", icon=":material/check_circle:")
else:
    st.error("FFmpeg was not found on PATH. Install it before processing media.", icon=":material/error:")

with st.container(border=True):
    st.subheader("Source")
    input_method = st.segmented_control(
        "Input method",
        ["Local file path", "Upload file"],
        default="Local file path",
        key="input_method",
    )
    input_path_text = ""
    uploaded_file = None
    if input_method == "Local file path":
        input_path_text = st.text_input(
            "Recording path",
            placeholder=r"C:\Meetings\weekly-meeting.mp4",
            help="Recommended for large recordings because the browser does not need to copy the file.",
        )
    else:
        uploaded_file = st.file_uploader(
            "Recording",
            type=["mp4", "avi", "mov", "mkv", "m4a", "wav", "mp3", "webm"],
            help="Use the local-path option for files above the Streamlit upload limit.",
        )

with st.form("compression_settings", border=True):
    st.subheader("Output settings")
    mode = st.segmented_control(
        "Processing mode",
        ["Extract transcription audio", "Compress video"],
        default="Extract transcription audio",
        key="processing_mode",
    )
    audio_bitrate = st.select_slider(
        "Audio bitrate",
        options=[48, 64, 96, 128],
        value=64,
        format_func=lambda value: f"{value} kbps",
        help="64 kbps is normally sufficient for speech transcription.",
    )

    crf = 28
    preset = "medium"
    height = None
    fps = None
    if mode == "Compress video":
        quality = st.select_slider(
            "Video quality",
            options=[32, 30, 28, 26, 23],
            value=28,
            format_func=lambda value: {
                32: "Smallest",
                30: "Smaller",
                28: "Balanced",
                26: "Higher",
                23: "Highest",
            }[value],
            help="Lower CRF values preserve more detail but create larger files.",
        )
        crf = quality
        preset = st.selectbox(
            "Encoding speed",
            ["veryfast", "fast", "medium", "slow"],
            index=2,
            help="Slower presets usually produce smaller files at the same quality.",
        )
        resolution_label = st.selectbox("Maximum resolution", ["Original", "1080p", "720p", "480p"], index=2)
        height = {"Original": None, "1080p": 1080, "720p": 720, "480p": 480}[resolution_label]
        fps_label = st.selectbox("Frame rate", ["Original", "30 fps", "24 fps", "15 fps"], index=3)
        fps = {"Original": None, "30 fps": 30, "24 fps": 24, "15 fps": 15}[fps_label]

    output_dir_text = st.text_input(
        "Output folder",
        value=str(DEFAULT_OUTPUT_DIR),
        help="A unique filename is generated; existing files are never overwritten.",
    )
    submitted = st.form_submit_button(
        "Process recording",
        type="primary",
        icon=":material/compress:",
        disabled=ffmpeg_path is None,
    )

if submitted:
    temporary_directory = None
    try:
        if input_method == "Local file path":
            if not input_path_text.strip():
                raise ValueError("Enter a recording path.")
            input_path = Path(input_path_text.strip().strip('"')).expanduser().resolve()
        else:
            if uploaded_file is None:
                raise ValueError("Choose a recording to upload.")
            temporary_directory = tempfile.TemporaryDirectory(prefix="ee499_compress_")
            input_path = Path(temporary_directory.name) / Path(uploaded_file.name).name
            input_path.write_bytes(uploaded_file.getbuffer())

        output_dir = Path(output_dir_text.strip().strip('"')).expanduser().resolve()
        with st.status("Processing recording…", expanded=True) as status:
            st.write(f"Input: `{input_path.name}`")
            result = process_file(input_path, output_dir, mode, audio_bitrate, crf, preset, height, fps)
            status.update(label="Processing complete", state="complete", expanded=False)

        st.session_state["compression_result"] = {
            "path": str(result.output_path),
            "input_bytes": result.input_bytes,
            "output_bytes": result.output_bytes,
            "reduction_percent": result.reduction_percent,
        }
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error), icon=":material/error:")
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()

result_data = st.session_state.get("compression_result")
if result_data:
    output_path = Path(result_data["path"])
    with st.container(border=True):
        st.subheader("Result")
        metrics = st.columns(3)
        metrics[0].metric("Original", human_size(result_data["input_bytes"]))
        metrics[1].metric("Output", human_size(result_data["output_bytes"]))
        metrics[2].metric("Size reduction", f"{result_data['reduction_percent']:.1f}%")
        st.code(str(output_path), language=None)
        if output_path.is_file():
            if output_path.suffix.lower() == ".m4a":
                st.audio(str(output_path))
            else:
                st.video(str(output_path))
        else:
            st.warning("The output file was moved or deleted after processing.")

st.info(
    "For transcription, use **Extract transcription audio** at **64 kbps**. "
    "Keep raw recordings outside Git and verify participant consent before processing.",
    icon=":material/info:",
)
