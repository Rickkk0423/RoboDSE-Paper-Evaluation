"""Preselected long-run convergence follow-up; never replace the frozen main grid."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import gzip
import json
from pathlib import Path
import shutil

from case_v3_main import digest, write_json, write_csv
from compute_diagnostics import summarize
from vlasim import HWConfig, MapConfig, DRAMModel, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def read_csv(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def worker(task, selected, root, snapshot, target_name='convergence_followup', lengths=(240, 480), previous_stats=None):
    root = Path(root)
    target = root / target_name
    wl = Pi05Workload()
    provider = NeuSimTiming(snapshot, wl, allow_analytical_siglip=True) if task['track'] == 'neusim_unsliced_hybrid' else None
    dram = DRAMModel(**task['calibration']['params'], version=task['calibration']['version'])
    rows = []
    with gzip.open(root / (task['id'] + '.jsonl.gz'), 'rt') as source, gzip.open(target / (task['id'] + '.jsonl.gz'), 'wt') as raw:
        for line in source:
            record = json.loads(line)
            if record['config_id'] not in selected:
                continue
            cfg = record['config']
            previous = record['result']
            base = previous
            if previous_stats is not None:
                previous = dict(S_mean=float(previous_stats[record['config_id']]['S_ms']) / 1000,
                                L_mean=float(previous_stats[record['config_id']]['L_ms']) / 1000)
            for requests in lengths:
                result = Simulator(HWConfig(**cfg['hardware']), MapConfig(**cfg['mapping']),
                    wl=wl, dram=dram, compute_time_fn=provider).run(requests, requests // 5, diagnostics=True)
                diag = summarize(result)
                rows.append(dict(parent_id=record['config_id'], task=task['id'], requests=requests,
                    warmup=requests // 5, S_ms=result['S_mean'] * 1000, L_ms=result['L_mean'] * 1000,
                    S_vs_previous_pct=(result['S_mean'] / previous['S_mean'] - 1) * 100,
                    L_vs_previous_pct=(result['L_mean'] / previous['L_mean'] - 1) * 100,
                    S_vs_120_pct=(result['S_mean'] / base['S_mean'] - 1) * 100,
                    L_vs_120_pct=(result['L_mean'] / base['L_mean'] - 1) * 100,
                    dit_GB_per_req=result['dit_GB_per_req'], dit_busy=result['dit_busy'], vlm_busy=result['vlm_busy'],
                    steady_active=diag['steady_round_mean_active_requests'],
                    **{f'round_{k}_ms': v for k, v in diag['steady_round_mean_ms'].items()}))
                raw.write(json.dumps(dict(parent_id=record['config_id'], requests=requests, config=cfg, result=result)) + '\n')
                previous = result
    write_csv(target / (task['id'] + '.csv'), rows)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--collect-only', action='store_true')
    ap.add_argument('--deep-selected', action='store_true', help='960/1920/3840 on selected allocations failing240/480 only')
    args = ap.parse_args()
    root = args.root.resolve()
    target_name = 'convergence_selected_deep' if args.deep_selected else 'convergence_followup'
    target = root / target_name
    if args.collect_only:
        collect(root, target)
        return
    target.mkdir(exist_ok=False)
    selected = {r['config_id_120'] for r in read_csv(root / 'convergence.csv')
                if max(abs(float(r['S_delta_pct'])), abs(float(r['L_delta_pct']))) > 1.}
    selected.update(r['config_id'] for r in read_csv(root / 'frontier.csv'))
    selected.update(r['config_id'] for r in read_csv(root / 'selected.csv'))
    lengths = (240, 480)
    previous_stats = None
    if args.deep_selected:
        chosen = {r['config_id'] for r in read_csv(root / 'selected.csv')}
        selected = {r['parent_id'] for r in read_csv(root / 'convergence_followup/unconverged.csv') if r['parent_id'] in chosen}
        previous_stats = {r['parent_id']: r for r in read_csv(root / 'convergence_followup/sweep.csv') if float(r['requests']) == 480}
        lengths = (960, 1920, 3840)
    manifest = json.loads((root / 'experiment_manifest.json').read_text())
    for name, expected in manifest['source_hashes'].items():
        if digest(Path(__file__).parent / name) != expected:
            raise ValueError('live source differs from executed grid: ' + name)
    write_json(target / 'experiment_manifest.json', dict(parent_manifest_sha256=digest(root / 'experiment_manifest.json'),
        source_sha256=digest(Path(__file__)), selected_ids=sorted(selected), requests=lengths, warmup_fraction=.2,
        snapshot_sha256=digest(args.snapshot / 'source_manifest.json'),
        selection='selected allocations failing240/480; no reranking' if args.deep_selected else 'all |30/120 S or L delta|>1%, every frozen120 frontier member, every selected allocation; no reranking; report 240/480 1% gate',
        analysis='Compare successive request counts; this is a finite deterministic-window stability test, not statistical confidence'))
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker, task, selected, str(root), str(args.snapshot.resolve()), target_name, lengths, previous_stats) for task in manifest['tasks']]
        for future in as_completed(futures):
            chunk = future.result()
            rows.extend(chunk)
            print('finished', len(rows), flush=True)
    write_csv(target / 'sweep.csv', rows)
    collect(root, target)


def collect(root, target):
    rows = read_csv(target / 'sweep.csv')
    for row in rows:
        for key in row:
            if key not in ('parent_id', 'task'):
                row[key] = float(row[key])
    manifest = json.loads((target / 'experiment_manifest.json').read_text())
    selected = manifest['selected_ids']
    lengths = manifest['requests']
    if len(rows) != len(lengths) * len(selected):
        raise ValueError('incomplete long follow-up')
    latest = [r for r in rows if r['requests'] == lengths[-1]]
    failed = [r for r in latest if max(abs(r['S_vs_previous_pct']), abs(r['L_vs_previous_pct'])) > 1.]
    chosen = {r['config_id'] for r in read_csv(root / 'selected.csv')}
    selected_rows = [r for r in latest if r['parent_id'] in chosen]
    write_csv(target / 'unconverged.csv', failed) if failed else (target / 'unconverged.csv').write_text('parent_id\n')
    write_json(target / 'status.json', dict(selected_configurations=len(selected), executed=len(rows),
        final_request_pair=lengths[-2:], checked_final_pair=len(latest), fail_1pct=len(failed),
        max_abs_S_delta_pct=max(abs(r['S_vs_previous_pct']) for r in latest),
        max_abs_L_delta_pct=max(abs(r['L_vs_previous_pct']) for r in latest),
        selected_max_abs_S_delta_pct=max(abs(r['S_vs_previous_pct']) for r in selected_rows),
        selected_max_abs_L_delta_pct=max(abs(r['L_vs_previous_pct']) for r in selected_rows),
        selected_fail_1pct=int(sum(max(abs(r['S_vs_previous_pct']), abs(r['L_vs_previous_pct'])) > 1. for r in selected_rows)),
        collector_source_sha256=digest(Path(__file__)),
        artifact_hashes={p.name: digest(p) for p in target.iterdir() if p.is_file() and p.name != 'status.json'}))


if __name__ == '__main__':
    main()
