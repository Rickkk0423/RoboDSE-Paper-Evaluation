"""Compact cold experiment evidence without losing original bytes or paths."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'results/_cold_storage_20261116'
TARGETS = [
    'results/v5_1/dse/shards', 'results/v6/dse/shards',
    'results/v6/band/shards', 'results/v6/band/control_repair/shards',
    'results/v5_1/heldout_input', 'results/v5_1/stage1_input',
    'results/v5_1/development_input', 'results/v5_1/calibration_input',
    'results/v5/selfcheck_input', 'results/v5/selfcheck_input_v2',
    'results/v4/p0a_input', 'results/v6/repair_input',
    'results/v6/seq_partial', 'results/v6/seq_attempt0',
    'results/v6/repair_attempt0',
]


def sha(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return sha(stream)


def save(path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, indent=2) + '\n')
    temp.replace(path)


def files_under(path, skip_links=False):
    files = []
    for item in sorted(path.rglob('*')):
        if item.is_symlink():
            if skip_links:
                continue
            raise RuntimeError(f'Refusing symbolic link: {item}')
        if item.is_file():
            files.append(item)
    return files


def verify_archive(archive, expected):
    seen = set()
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise RuntimeError(f'Unexpected archive member: {member.name}')
            with tar.extractfile(member) as stream:
                actual = sha(stream)
            if actual != expected[member.name]['sha256']:
                raise RuntimeError(f'Archive hash mismatch: {member.name}')
            seen.add(member.name)
    if seen != set(expected):
        raise RuntimeError('Missing archive members')


def compact():
    STORE.mkdir(exist_ok=True)
    manifest = STORE / 'cleanup_manifest.json'
    if manifest.exists():
        raise RuntimeError('Existing cleanup manifest; refusing to overwrite')
    targets = [ROOT / p for p in TARGETS if (ROOT / p).is_dir()]
    protected = {}
    for path in files_under(ROOT / 'results', skip_links=True):
        if STORE in path.parents or any(t in path.parents for t in targets):
            continue
        protected[str(path.relative_to(ROOT))] = file_sha(path)
    for base in ('docs', 'vlasim', 'tests', 'configs'):
        for path in files_under(ROOT / base, skip_links=True):
            if '__pycache__' not in path.parts:
                protected[str(path.relative_to(ROOT))] = file_sha(path)
    save(STORE / 'preserved_files.json', protected)
    report = dict(started=time.time(), mode='lossless_verified_cold_storage',
                  archives=[], deleted_caches=[], protected_files=len(protected))
    save(manifest, report)
    for target in targets:
        name = str(target.relative_to(ROOT))
        print(f'ARCHIVING {name}', flush=True)
        files = files_under(target)
        entries = {}
        for path in files:
            stat = path.stat()
            entries[str(path.relative_to(ROOT))] = dict(
                sha256=file_sha(path), bytes=stat.st_size,
                allocated_bytes=stat.st_blocks * 512,
                mtime_ns=stat.st_mtime_ns, mode=stat.st_mode & 0o777)
        archive = STORE / (name.replace('/', '__') + '.tar.gz')
        partial = archive.with_suffix('.partial')
        with tarfile.open(partial, 'w:gz', compresslevel=6, dereference=True) as tar:
            for path in files:
                tar.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
        print(f'VERIFYING {name}: {len(files)} files', flush=True)
        verify_archive(partial, entries)
        partial.replace(archive)
        index = archive.with_suffix('.index.json')
        save(index, entries)
        row = dict(source=name, archive=str(archive.relative_to(ROOT)),
                   index=str(index.relative_to(ROOT)), files=len(files),
                   original_bytes=sum(e['bytes'] for e in entries.values()),
                   original_allocated_bytes=sum(e['allocated_bytes'] for e in entries.values()),
                   archive_bytes=archive.stat().st_size, sha256=file_sha(archive),
                   verified=True, removed=False)
        report['archives'].append(row)
        save(manifest, report)
        # Refuse deletion if any source has changed since it was archived.
        for path in files:
            if file_sha(path) != entries[str(path.relative_to(ROOT))]['sha256']:
                raise RuntimeError(f'Source changed during archiving: {path}')
        if set(files_under(target)) != set(files):
            raise RuntimeError(f'Directory changed during archiving: {target}')
        shutil.rmtree(target)
        row['removed'] = True
        save(manifest, report)
        print(f'COMPACTED {name}: {row["original_allocated_bytes"] / 2**30:.3f} GiB -> '
              f'{row["archive_bytes"] / 2**30:.3f} GiB', flush=True)
    caches = [ROOT / '.pytest_cache']
    for base in ('vlasim', 'tests', 'scripts'):
        caches.extend((ROOT / base).rglob('__pycache__'))
    for cache in sorted(caches, key=lambda p: len(p.parts), reverse=True):
        if cache.is_dir() and not cache.is_symlink():
            report['deleted_caches'].append(str(cache.relative_to(ROOT)))
            shutil.rmtree(cache)
    save(manifest, report)
    finish_verification(report, protected, manifest)


def finish_verification(report, protected, manifest):
    changed = [p for p, digest in protected.items() if file_sha(ROOT / p) != digest]
    report['finder_metadata_changed'] = [p for p in changed if Path(p).name == '.DS_Store']
    changed = [p for p in changed if Path(p).name != '.DS_Store']
    if changed:
        raise RuntimeError(f'Protected files changed: {changed}')
    report.update(completed=time.time(), protected_files_unchanged=True,
                  saved_allocated_bytes=sum(r['original_allocated_bytes'] -
                                            (ROOT / r['archive']).stat().st_blocks * 512 -
                                            (ROOT / r['index']).stat().st_blocks * 512
                                            for r in report['archives']))
    save(manifest, report)
    print(json.dumps({k: v for k, v in report.items() if k != 'archives'}, indent=2), flush=True)


def restore(source):
    report = json.loads((STORE / 'cleanup_manifest.json').read_text())
    rows = [r for r in report['archives'] if source == 'all' or r['source'] == source]
    if not rows:
        raise RuntimeError('Unknown archived source')
    for row in rows:
        archive = ROOT / row['archive']
        entries = json.loads((ROOT / row['index']).read_text())
        if file_sha(archive) != row['sha256']:
            raise RuntimeError('Archive checksum mismatch')
        verify_archive(archive, entries)
        for name in entries:
            path = ROOT / name
            if not path.resolve().is_relative_to(ROOT) or path.exists() or path.is_symlink():
                raise RuntimeError(f'Refusing unsafe path or overwrite: {name}')
        with tarfile.open(archive, 'r|gz') as tar:
            for member in tar:
                path = ROOT / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, path.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                path.chmod(entries[member.name]['mode'])
        if any(file_sha(ROOT / p) != e['sha256'] for p, e in entries.items()):
            raise RuntimeError('Restoration verification failed')
        print(f'RESTORED {row["source"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--restore', metavar='SOURCE_OR_all')
    parser.add_argument('--verify-final', action='store_true')
    args = parser.parse_args()
    if sum((args.compact, bool(args.restore), args.verify_final)) != 1:
        parser.error('Choose --compact, --restore SOURCE_OR_all or --verify-final')
    if args.compact:
        compact()
    elif args.restore:
        restore(args.restore)
    else:
        manifest = STORE / 'cleanup_manifest.json'
        report = json.loads(manifest.read_text())
        if not all(r['removed'] and r['verified'] for r in report['archives']):
            raise RuntimeError('Compaction has incomplete archive entries')
        protected = json.loads((STORE / 'preserved_files.json').read_text())
        finish_verification(report, protected, manifest)
