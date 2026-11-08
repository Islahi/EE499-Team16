#!/usr/bin/env python3
"""Download open-access references listed in paper_manifest.json. No third-party packages."""
from pathlib import Path
import json, urllib.request
HERE=Path(__file__).resolve().parent
papers=json.loads((HERE/'paper_manifest.json').read_text(encoding='utf8'))['papers']
for p in papers:
    dest=HERE/p['file']
    if dest.exists() and dest.read_bytes()[:4]==b'%PDF':
        print('EXISTS',dest.name)
        continue
    req=urllib.request.Request(p['url'],headers={'User-Agent':'Mozilla/5.0 (academic reference download)'})
    try:
        with urllib.request.urlopen(req,timeout=35) as resp:
            data=resp.read()
        if not data.startswith(b'%PDF'):
            print('FAILED',p['id'],'Response was not a PDF; use',p['landing'])
            continue
        dest.write_bytes(data)
        print('SAVED',dest.name,len(data),'bytes')
    except Exception as exc:
        print('FAILED',p['id'],str(exc))
        print('  Manual download page:',p['landing'])
