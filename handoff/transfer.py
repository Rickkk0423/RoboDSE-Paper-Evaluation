"""Copy project snapshots and compare every payload file by SHA-256."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/mr.meeseeks/orca/workspaces/RoboDSE/Neusim_ramulator_DSE')
BACKEND = SOURCE.parent / 'Ramulator_parallel'
EXCLUDED = {'.git', '.venv', '.pytest_cache', '__pycache__', '.DS_Store'}
DOWNLOAD_NAMES = ['NEXT_STEPS_V7.md', 'RAMULATOR_STAGE3_DIAG_NEXT_STEPS.md',
                  'RAMULATOR_STAGE3_DIAG_NEXT_STEPS (1).md']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def entries(root):
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(files + [d for d in dirs if (Path(base) / d).is_symlink()]):
            if name not in EXCLUDED:
                yield Path(base) / name


def copy_tree(source, dest):
    dest.mkdir(parents=True, exist_ok=True)
    command = ['rsync', '-a']
    for name in sorted(EXCLUDED):
        command += ['--exclude', name]
    subprocess.run(command + [str(source) + '/', str(dest) + '/'], check=True)


def run(copy=False):
    if copy and (ROOT / 'handoff/transfer_manifest.json').exists():
        raise RuntimeError('Initial transfer already recorded; use verify_snapshot.py instead of overwriting it')
    groups = [(SOURCE, ROOT), (BACKEND, ROOT / 'dependencies/Ramulator_parallel')]
    if copy:
        for source, dest in groups:
            copy_tree(source, dest)
        downloads = Path('/Users/mr.meeseeks/Downloads')
        for name in DOWNLOAD_NAMES:
            source = downloads / name
            subprocess.run(['cp', '-p', str(source), str(ROOT / 'handoff/original_inputs' / name)], check=True)
            groups.append((source, ROOT / 'handoff/original_inputs' / name))
    else:
        for name in DOWNLOAD_NAMES:
            groups.append((Path('/Users/mr.meeseeks/Downloads') / name,
                           ROOT / 'handoff/original_inputs' / name))
    records, errors = [], []
    for source, dest in groups:
        paths = entries(source) if source.is_dir() else [source]
        for path in paths:
            target = dest / path.relative_to(source) if source.is_dir() else dest
            record = {'source': str(path), 'destination': str(target.relative_to(ROOT))}
            if path.is_symlink():
                record.update(kind='symlink', target=os.readlink(path))
                ok = target.is_symlink() and os.readlink(target) == record['target'] and target.exists()
            else:
                record.update(kind='file', bytes=path.stat().st_size, sha256=digest(path))
                ok = target.is_file() and target.stat().st_size == record['bytes'] and digest(target) == record['sha256']
            record['passed'] = ok
            records.append(record)
            if not ok:
                errors.append(record['destination'])
    manifest = {'source': str(SOURCE), 'destination': str(ROOT), 'mode': 'verified_copy_originals_retained',
                'exclusions': sorted(EXCLUDED), 'files_and_links': len(records),
                'regular_file_bytes': sum(r.get('bytes', 0) for r in records),
                'passed': not errors, 'mismatches': errors, 'records': records}
    (ROOT / 'handoff/transfer_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'records'}, indent=2), flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    run('--copy' in sys.argv)
