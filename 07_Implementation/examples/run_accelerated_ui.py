"""Launch the isolated acceleration build from any working directory."""
from pathlib import Path
import multiprocessing
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src_accelerated.ui import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
