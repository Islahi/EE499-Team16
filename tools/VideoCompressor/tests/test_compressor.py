import tempfile
import unittest
from pathlib import Path

from compressor import build_audio_command, build_video_command, unique_output_path


class CompressorTests(unittest.TestCase):
    def test_audio_command_disables_video(self):
        command = build_audio_command("ffmpeg", Path("input.mp4"), Path("output.m4a"), 64)
        self.assertIn("-vn", command)
        self.assertEqual(command[command.index("-b:a") + 1], "64k")

    def test_video_command_applies_optional_filters(self):
        command = build_video_command(
            "ffmpeg",
            Path("input.mp4"),
            Path("output.mp4"),
            crf=28,
            preset="medium",
            audio_bitrate_kbps=64,
            height=720,
            fps=15,
        )
        self.assertEqual(command[command.index("-vf") + 1], "scale=-2:720,fps=15")
        self.assertEqual(command[command.index("-crf") + 1], "28")

    def test_unique_output_path_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            (output_directory / "meeting_audio.m4a").touch()
            result = unique_output_path(output_directory, "meeting_audio", ".m4a")
            self.assertEqual(result.name, "meeting_audio_2.m4a")


if __name__ == "__main__":
    unittest.main()
