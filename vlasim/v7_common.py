"""V7 output isolation, resumable evidence and archive-aware preservation."""
import csv
import hashlib
import json
from pathlib import Path

from v6_common import load, write_json, digest

ROOT = Path('results/v7')
V6 = Path('results/v6')
BOXES = [(l, s) for l in (100, 150, 200, 250, 300)
         for s in (50, 75, 100, 150, 200) if s <= l]


def write_csv(path, rows, comment=None):
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as stream:
        if comment:
            stream.write('# ' + comment.replace('\n', ' ') + '\n')
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(line for line in stream if not line.startswith('#')))


def truth(x):
    return x is True or x == 'True'


def token(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def checkpoint(path, identity):
    path = Path(path)
    if not path.exists():
        return None
    saved = load(path)
    if saved['identity'] != identity:
        raise RuntimeError('Checkpoint inputs/source changed: ' + str(path))
    for name, expected in saved['hashes'].items():
        if digest(path.parent / name) != expected:
            raise RuntimeError('HARD_STOP_checkpoint_hash ' + str(path.parent / name))
    return saved


def preservation(verify_archives=False):
    store = Path('results/_cold_storage_20261116')
    archives = load(store / 'cleanup_manifest.json')['archives']
    index = {}
    for row in archives:
        if verify_archives and digest(row['archive']) != row['sha256']:
            raise RuntimeError('HARD_STOP_cold_archive_changed')
        index.update({name: item['sha256'] for name, item in load(row['index']).items()})
    reports = []
    cache = {}
    for root in (V6, Path('results/v5_1'), Path('results/v5'), Path('results/v4'),
                 Path('results/case_v3_complete')):
        manifest = load(root / 'delivery_manifest.json')
        files = ({str(root / p): sha for p, sha in manifest['artifacts_sha256'].items()}
                 if 'artifacts_sha256' in manifest else manifest['files'])
        sources = manifest.get('sources_sha256', manifest.get('source_sha256',
                                      manifest.get('implementation_sha256', {})))
        if isinstance(sources, dict):
            files.update(sources)
        for name, expected in files.items():
            if name not in cache:
                cache[name] = digest(name) if Path(name).is_file() else index.get(name)
            if cache[name] != expected:
                raise RuntimeError('HARD_STOP_prior_delivery_changed ' + name)
        reports.append(dict(root=str(root), checked=len(files), passed=True))
    return dict(passed=True, deliveries=reports, archive_files=len(index),
                archive_checksums_verified=verify_archives)


def candidates():
    return read_csv(ROOT / 'inputs/candidate_points.csv')


def resource(row, sram=False):
    result = (int(row['n_cores']), float(row['actual_peak_GBps']))
    if sram:
        result += (float(row['sram_mb']) + int(row['n_cores']) *
                   float(row['local_kb']) * 1024 / 1e6,)
    return result


def dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def feasible(row, lmax, smax, protocol):
    if protocol == 'latency_only':
        return row['mode'] == 'serial' and float(row['L_s']) * 1000 <= smax + 1e-9
    return (float(row['L_s']) * 1000 <= lmax + 1e-9 and
            float(row['S_s']) * 1000 <= smax + 1e-9)


def pareto(rows, sram=False):
    vectors = {resource(r, sram) for r in rows}
    keep = {v for v in vectors if not any(dominates(q, v) for q in vectors)}
    return [r for r in rows if resource(r, sram) in keep]


def summary(row):
    return dict(point_id=row['point_id'], hardware_id=row['hardware_id'], memory=row['memory'],
                n_cores=int(row['n_cores']), BW_peak_GBps=float(row['actual_peak_GBps']),
                sram_shared_MB=float(row['sram_mb']), private_KB_per_core=float(row['local_kb']),
                total_SRAM_MB=resource(row, True)[2], mode=row['mode'],
                vlm_cores=int(row['vlm_cores']), k=int(row['dit_stages']),
                batching=truth(row['dit_batching']), L_ms=float(row['L_s']) * 1000,
                S_ms=float(row['S_s']) * 1000, period_s=float(row['T_s']),
                conditional_status=row['conditional_status'])
