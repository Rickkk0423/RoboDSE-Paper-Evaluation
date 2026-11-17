"""Verify the copied payload without reading any original source directories."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELOCATED = {
    'README.md': 'handoff/original_inputs/DSE_README_ORIGINAL.md',
    'vlasim/vlasim_dse.egg-info/SOURCES.txt': 'handoff/original_inputs/DSE_EGG_SOURCES_ORIGINAL.txt',
}


def verify():
    manifest = json.loads((ROOT / 'handoff/transfer_manifest.json').read_text())
    mismatches = []
    for record in manifest['records']:
        path = ROOT / RELOCATED.get(record['destination'], record['destination'])
        if record['kind'] == 'symlink':
            ok = path.is_symlink() and os.readlink(path) == record['target'] and path.exists()
        else:
            ok = path.is_file() and path.stat().st_size == record['bytes']
            if ok:
                h = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                        h.update(block)
                ok = h.hexdigest() == record['sha256']
        if not ok:
            mismatches.append(record['destination'])
    result = dict(passed=not mismatches, checked=len(manifest['records']),
                  root=str(ROOT), original_directories_read=False,
                  relocated_originals=RELOCATED, mismatches=mismatches)
    (ROOT / 'handoff/validation/snapshot_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(verify())
