# Meeting Records

This folder separates raw meeting material from reviewed meeting documentation.

## Folders

- `Raw_Recordings/` — local audio/video recordings and unreviewed machine transcripts.
- `Meeting_Minutes/` — agendas, talking points, reviewed transcripts, and finalized meeting minutes.

## Workflow

1. Obtain the participants' permission before recording.
2. Keep the original recording under `Raw_Recordings/` while it is needed.
3. If the recording is large, use `tools/VideoCompressor/` to extract a transcription-ready M4A or create a smaller video.
4. Transcribe it with `tools/VideoTranscriber/`.
5. Verify names, technical terms, numerical values, decisions, owners, and deadlines against the recording.
6. Copy and fill `Meeting_Minutes/EE499MeetingMinutes.docx`, preserving the official Word form and its existing sections.
7. Do not treat an AI-generated transcript or summary as approved minutes until a team member reviews it.

Raw audio and video are ignored by Git because they may be large or sensitive. If the team needs to preserve a recording, use an approved private storage location and record only the reference/location in the minutes.

## AI shortcut

Tell an AI working with this repository:

> **Write meeting minutes from `[raw filename]`.**

The shorter instruction **“write MM from `[raw filename]`”** has the same meaning. Repository-aware AI assistants must follow the meeting-minutes workflow in `AI_GUIDE.md` and use `Meeting_Minutes/EE499MeetingMinutes.docx` as the authoritative template.

Always identify the source filename when multiple raw meetings exist. Without it, the AI may need to ask which recording or transcript is intended.

Generated documents must use neutral project terminology such as **implementation plan**, **design baseline**, or **project requirements**. Internal drafting labels and internal filenames must not appear in deliverables, and internal meetings must omit advisors who did not participate. This presentation rule does not permit claiming that internal work was externally approved.
