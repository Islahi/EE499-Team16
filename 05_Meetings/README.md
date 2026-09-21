# Meeting Records

This folder separates raw meeting material from reviewed meeting documentation.

## Folders

- `Raw_Recordings/` — local audio/video recordings and unreviewed machine transcripts.
- `Meeting_Minutes/` — agendas, talking points, reviewed transcripts, and finalized meeting minutes.

## Workflow

1. Obtain the participants' permission before recording.
2. Keep the original recording under `Raw_Recordings/` while it is needed.
3. Transcribe it with `tools/VideoTranscriber/`.
4. Verify names, technical terms, numerical values, decisions, owners, and deadlines against the recording.
5. Save the reviewed minutes under `Meeting_Minutes/` using `YYYY-MM-DD_Descriptive_Name.md` or the required course template.
6. Do not treat an AI-generated transcript or summary as approved minutes until a team member reviews it.

Raw audio and video are ignored by Git because they may be large or sensitive. If the team needs to preserve a recording, use an approved private storage location and record only the reference/location in the minutes.

## AI shortcut

Tell an AI working with this repository:

> **Write meeting minutes from `[raw filename]`.**

The shorter instruction **“write MM from `[raw filename]`”** has the same meaning. Repository-aware AI assistants must follow the meeting-minutes workflow in `AI_GUIDE.md` and use `Meeting_Minutes/MEETING_MINUTES_TEMPLATE.md`.

Always identify the source filename when multiple raw meetings exist. Without it, the AI may need to ask which recording or transcript is intended.
