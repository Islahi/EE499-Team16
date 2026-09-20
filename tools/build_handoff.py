#!/usr/bin/env python3
"""Build a portable AI/human handoff ZIP from the repository working tree."""
from pathlib import Path
from datetime import date
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "Exports"
EXPORTS.mkdir(exist_ok=True)
OUT = EXPORTS / f"EE499-Team16-Handoff-{date.today().isoformat()}.zip"

EXCLUDED_DIRS = {'.git', 'Exports', '__pycache__', '.venv', 'venv', '.idea', '.vscode', '.ipynb_checkpoints'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.tmp', '.temp', '.part'}

def excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith('~$'):
        return True
    return False

with zipfile.ZipFile(OUT, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or excluded(path):
            continue
        zf.write(path, path.relative_to(ROOT.parent))

print(OUT)
