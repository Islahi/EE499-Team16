"""Repair a completed archived run omitted from session.json after a GUI handoff issue.

Usage: python RECOVER_ARCHIVED_RUN.py "C:\\path\\to\\Results\\Sessions\\<session>"

The script never changes canonical run CSV, the optimizer result or HTML. It
writes a timestamped backup of session.json before adding only missing entries.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import csv
import json
import shutil
import sys


def recover(session_folder: Path) -> list[str]:
    root = Path(session_folder).resolve(strict=True)
    manifest_path = root / 'session.json'
    if not manifest_path.is_file():
        raise ValueError(f'Not a saved BESS study: {root}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    restored = []
    for category, key in [('optimization', 'optimization_runs'), ('simulation', 'simulation_runs')]:
        for folder in sorted((root / category).glob('run_*')) if (root / category).is_dir() else []:
            if not folder.is_dir() or folder.is_symlink():
                continue
            relative = folder.relative_to(root).as_posix()
            existing = next((row for row in manifest.get(key, [])
                             if row.get('path', '').replace('\\', '/') == relative), None)
            if existing is not None and not (
                existing.get('status') == 'failed'
                and 'not JSON serializable' in str(existing.get('error', ''))
            ):
                continue
            # Recover only fully exported runs, never partial experiments.
            if not all((folder / name).is_file() for name in
                       ('summary.md', 'metrics.csv', 'dashboard_run.json')):
                continue
            data = json.loads((folder / 'dashboard_run.json').read_text(encoding='utf-8-sig'))
            if data.get('kind') != category:
                continue
            with (folder / 'metrics.csv').open(encoding='utf-8-sig', newline='') as stream:
                metrics = {row['metric']: row['value'] for row in csv.DictReader(stream)}
            if metrics.get('duration_hours') is None or metrics.get('annual_total_cost') is None:
                continue
            # Do not convert arbitrary failed optimizations into successes.
            # The numerical result must have completed and passed its own
            # feasibility check before a JSON-only registration failure.
            if metrics.get('feasible', '').strip().lower() != 'true':
                continue
            summary_text = (folder / 'summary.md').read_text(encoding='utf-8-sig')
            if category == 'optimization' and '- Success: True' not in summary_text:
                continue
            record = {
                'path': relative,
                'status': 'recovered_complete',
                'context': data.get('context'),
                'optimizer': data.get('optimizer'),
                'metrics': metrics,
                'completed_at': datetime.fromtimestamp(folder.stat().st_mtime).astimezone().isoformat(timespec='seconds'),
                'recovery_note': 'Canonical run exports existed, but GUI completion registration was missing',
            }
            if existing is not None:
                record['recovered_from_error'] = existing.get('error')
                existing.clear()
                existing.update(record)
            else:
                manifest.setdefault(key, []).append(record)
            restored.append(relative)
    if restored:
        backup = manifest_path.with_name('session.json.before_recovery_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        shutil.copy2(manifest_path, backup)
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(dir=root, mode='w', encoding='utf-8', delete=False) as temporary:
            json.dump(manifest, temporary, indent=2)
            temp_path = Path(temporary.name)
        temp_path.replace(manifest_path)
    return restored


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python RECOVER_ARCHIVED_RUN.py <saved-session-folder>')
    items = recover(Path(sys.argv[1]))
    print('Recovered:', ', '.join(items) if items else 'Nothing to recover; all runs are already registered.')
