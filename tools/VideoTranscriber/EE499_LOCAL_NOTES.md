# EE499 Local Integration Notes

This directory vendors the MIT-licensed [DataAnts-AI VideoTranscriber](https://github.com/DataAnts-AI/VideoTranscriber) for local meeting transcription.

- **Upstream commit:** `d1e1fedcaeefa812868cc73fa216b3424c7cb915`
- **Vendored on:** 2026-09-21
- **License:** See `LICENSE` in this directory.
- **Local modifications at import:** Only this integration note was added; upstream Git metadata was removed.

## Recommended project workflow

1. Create a dedicated Python virtual environment inside this directory.
2. Install FFmpeg and the dependencies documented in the upstream `README.md` and `INSTALLATION.md`.
3. Start the application with `streamlit run app.py`.
4. Process recordings from `05_Meetings/Raw_Recordings/`.
5. Use Whisper `small` or `medium` when the computer can support it; technical names and mixed Arabic/English speech still require manual review.
6. Save only reviewed meeting records under `05_Meetings/Meeting_Minutes/`.
7. Clear the application's transcription cache after sensitive meetings.

## Important limitations

- Transcripts, speaker labels, and summaries can be wrong.
- Diarization labels speakers generically and requires a Hugging Face token/model access.
- The application's Hugging Face summarization model runs locally after its model files are downloaded, despite the interface calling the option “Online.”
- Caching may retain transcript text locally.
- The upstream dependencies are broadly versioned rather than locked, so installation may change over time.
- Do not expose the Streamlit service to the public network; use it on localhost.
- Do not use generated summaries as official minutes without checking the recording.

## Updating the vendored copy

Do not run `git pull` inside this directory because it is not a nested repository. To update it, compare against a newer upstream commit, preserve this file and the upstream license, review the incoming changes, and record the new commit hash here.
