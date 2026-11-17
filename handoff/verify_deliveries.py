"""Audit frozen deliveries without writing to any published result tree."""
import hashlib
import json
import os
from pathlib import Path
from verify_snapshot import RELOCATED

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def preservation():
    store = ROOT / 'results/_cold_storage_20261116'
    archives = json.loads((store / 'cleanup_manifest.json').read_text())['archives']
    index = {}
    for row in archives:
        if digest(ROOT / row['archive']) != row['sha256']:
            raise RuntimeError('Cold archive changed: ' + row['archive'])
        index.update({name: item['sha256'] for name, item in
                      json.loads((ROOT / row['index']).read_text()).items()})
    reports, cache = [], {}
    for name in ('v6', 'v5_1', 'v5', 'v4', 'case_v3_complete'):
        root = Path('results') / name
        manifest = json.loads((ROOT / root / 'delivery_manifest.json').read_text())
        files = ({str(root / p): sha for p, sha in manifest['artifacts_sha256'].items()}
                 if 'artifacts_sha256' in manifest else dict(manifest['files']))
        sources = manifest.get('sources_sha256', manifest.get('source_sha256',
                               manifest.get('implementation_sha256', {})))
        if isinstance(sources, dict):
            files.update(sources)
        for path, expected in files.items():
            if path not in cache:
                target = ROOT / RELOCATED.get(path, path)
                if not target.resolve().is_relative_to(ROOT):
                    raise RuntimeError('Unexpected external manifest path: ' + path)
                cache[path] = digest(target) if target.is_file() else index.get(path)
            if cache[path] != expected:
                raise RuntimeError('Historical delivery changed: ' + path)
        reports.append(dict(root=str(root), checked=len(files), passed=True))
    return dict(passed=True, deliveries=reports, archive_files=len(index),
                archive_checksums_verified=True, relocated_originals=RELOCATED)


def main():
    os.chdir(ROOT)
    historical = preservation()
    manifest = json.loads((ROOT / 'results/v7/delivery_manifest.json').read_text())
    expected = {ROOT / 'results/v7' / p: sha for p, sha in manifest['artifacts_sha256'].items()}
    expected.update({ROOT / p: sha for p, sha in manifest['sources_sha256'].items()})
    mismatches = []
    for path, sha in expected.items():
        if digest(path) != sha:
            mismatches.append(str(path.relative_to(ROOT)))
    result = dict(passed=historical['passed'] and not mismatches, historical=historical,
                  v7=dict(artifacts=len(manifest['artifacts_sha256']),
                          sources=len(manifest['sources_sha256']), mismatches=mismatches))
    (ROOT / 'handoff/validation/delivery_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
