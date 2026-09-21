# Meeting Media Compressor

A local Streamlit interface for compressing meeting recordings with FFmpeg.

## Features

- extract transcription-ready AAC audio as M4A;
- compress video to H.264 MP4;
- optionally reduce video resolution and frame rate;
- process large recordings directly from a local path;
- generate unique output filenames instead of overwriting files;
- preview the output and report its size reduction.

All processing is local. The tool does not send recordings to an external service.

## Requirements

- Python with Streamlit;
- FFmpeg available on `PATH`.

The existing `tools/venv` environment can run this app once its dependencies are healthy.

## Run from the repository root

```cmd
tools\venv\Scripts\python.exe -m streamlit run tools\VideoCompressor\app.py
```

Or, from the `tools` directory with the environment activated:

```cmd
python -m streamlit run VideoCompressor\app.py
```

## Recommended transcription preset

- Processing mode: **Extract transcription audio**
- Audio bitrate: **64 kbps**
- Output: `.m4a`

The default output directory is `05_Meetings/Raw_Recordings/`. Raw media in that folder is ignored by Git.
