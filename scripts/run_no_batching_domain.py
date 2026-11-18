"""Fresh, unpruned three-arm search over the hardware identities retained by V7."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vlasim'))
from v7_common import BOXES, dominates, feasible, pareto, read_csv, resource, summary, write_csv, write_json
from v6_band import engine_from_row
from v51_dse import evaluate, semantic_key, summarize
from ablate_no_batching import allowed


def mappings(cores):
    return [('serial', cores, 1, True)] + [
        ('pipelined', split, k, batch) for split in range(1, cores)
        for k, batch in ((1, True), (2, True), (3, True), (2, False), (3, False))]


def shard(task):
    memory, templates, out, calibration = task
    out = Path(out)
    folder = out / 'shards' / memory
    folder.mkdir(parents=True, exist_ok=True)
    configs, points, cache = [], [], {}
    for template in templates:
        hardware = template['hardware_id']
        for mode, split, k, batch in mappings(int(template['n_cores'])):
            cid = f'{hardware}_{mode}_{split}_{k}_{batch}'
            row = dict(template, mode=mode, vlm_cores=str(split), dit_stages=str(k),
                       dit_batching=str(batch), config_id=cid, pruning_scope='none',
                       candidate_source='fresh_unpruned_retained_hardware_domain')
            engine = engine_from_row(row, out / 'periodic.dylib', calibrations=calibration)
            config = dict(config_id=cid, hardware_id=hardware, mode=mode, vlm_cores=split,
                          k=k, batching=batch)
            if not engine.reference.sram_ok:
                configs.append(dict(config, status='static_infeasible'))
                continue
            key = semantic_key(engine)
            if key not in cache:
                cache[key] = evaluate(engine, folder / 'runs' / key)
                if len(cache) % 50 == 0:
                    print(memory, 'unique semantics', len(cache), flush=True)
            value = cache[key]
            configs.append(dict(config, status=value['search']['status'], semantic_id=key))
            for p in value['curve']:
                if not p['gate']['pass_gate']:
                    continue
                points.append(dict(row, **p['metrics'], factor=p['factor'], T_s=p['T_s'],
                    L_s=p['gate']['L_mean_s'], S_s=p['gate']['S_mean_s'],
                    Tmin_s=value['search']['Tmin_s'], status=value['search']['status'],
                    point_id=f'{cid}_f{p["factor"]}', semantic_id=key, curve_gate=True,
                    raw=str(folder / 'runs' / key / 'requests.npz'), raw_sha256=value['raw_sha256'],
                    timing_scope='fresh 480-request period search; frontier checked separately at 960 requests'))
    write_csv(folder / 'configurations.csv', configs)
    write_csv(folder / 'candidate_points.csv', points)
    report = dict(memory=memory, hardware=len(templates), configurations=len(configs),
                  semantics=len(cache), candidates=len(points), statuses=dict(Counter(c['status'] for c in configs)))
    write_json(folder / 'summary.json', report)
    print('FINISHED', report, flush=True)
    return report


def compare(points):
    comparisons, fronts = [], []
    for eligibility in ('all_v7_eligible', 'refreshed_only'):
        population = [r for r in points if eligibility == 'all_v7_eligible' or
                      r['conditional_status'] == 'refreshed_median_eligible']
        for l, s in BOXES:
            pools = {a: [r for r in population if allowed(r, a) and feasible(
                r, l, s, 'latency_only' if a == 'serial' else 'task_aware')]
                for a in ('serial', 'no_batching', 'full')}
            for sram in (False, True):
                base = dict(eligibility=eligibility, Lmax_ms=l, Smax_ms=s,
                            dimensions='cores_BW_SRAM' if sram else 'cores_BW')
                pf = {a: pareto(p, sram=sram) for a, p in pools.items()}
                for a, rows in pf.items():
                    fronts.extend(dict(**base, arm=a, **summary(r)) for r in rows)
                for a, b in (('serial', 'no_batching'), ('no_batching', 'full'), ('serial', 'full')):
                    av, bv = ({resource(r, sram) for r in pf[x]} for x in (a, b))
                    relation = ('identical' if av == bv else 'lat_infeasible_task_feasible' if not av
                                else 'task_strictly_better' if any(dominates(y, x) for y in bv for x in av)
                                else 'task_extends')
                    comparisons.append(dict(**base, baseline=a, alternative=b, relation=relation,
                        baseline_feasible=len(pools[a]), alternative_feasible=len(pools[b]),
                        baseline_vectors=len(av), alternative_vectors=len(bv)))
    return comparisons, fronts


def run(out, workers):
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'results/v7/inputs/candidate_points.csv'
    calfile = ROOT / 'results/v7/inputs/calibration.json'
    files = [source, calfile, Path(__file__), ROOT / 'scripts/ablate_no_batching.py']
    files += sorted((ROOT / 'vlasim').rglob('*.py')) + [ROOT / 'vlasim/v6_periodic.cpp']
    files += sorted(p for p in (ROOT / '.native/compute').rglob('*') if p.is_file())
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    mp = out / 'input_manifest.json'
    if mp.exists() and json.loads(mp.read_text()) != manifest:
        raise RuntimeError('Inputs changed; use a fresh output directory')
    write_json(mp, manifest)
    subprocess.run(['c++', '-O2', '-ffp-contract=off', '-std=c++17', '-shared', '-fPIC',
                    'vlasim/v6_periodic.cpp', '-o', str(out / 'periodic.dylib')], check=True)
    templates = {r['hardware_id']: r for r in read_csv(source)}
    calibration = json.loads(calfile.read_text())
    tasks = [(m, [r for _, r in sorted(templates.items()) if r['memory'] == m], str(out), calibration)
             for m in sorted({r['memory'] for r in templates.values()})]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        shards = list(pool.map(shard, tasks))
    points = [r for m, *_ in tasks for r in read_csv(out / 'shards' / m / 'candidate_points.csv')]
    configs = [r for m, *_ in tasks for r in read_csv(out / 'shards' / m / 'configurations.csv')]
    comparisons, fronts = compare(points)
    selected = {r['point_id'] for r in fronts}
    checks, checked, rejected = {}, [], set()
    for row in points:
        if row['point_id'] not in selected:
            continue
        key = (row['memory'], row['semantic_id'], row['factor'])
        if key not in checks:
            engine = engine_from_row(row, out / 'periodic.dylib', calibrations=calibration)
            result = engine.run(float(row['T_s']), 960, 192)
            check = summarize(result, float(row['T_s']), engine.k)
            raw = out / 'checks960' / f'{key[0]}_{key[1]}_{key[2]}.npz'
            raw.parent.mkdir(exist_ok=True)
            np.savez_compressed(raw, requests=np.array([[r[n] for n in
                ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s')] for r in result['requests']]))
            check.update(raw=str(raw), raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
            write_json(raw.with_suffix('.json'), check)
            checks[key] = check
        check = checks[key]
        error = max(abs(check['gate'][n] - float(row[c])) / max(abs(float(row[c])), 1e-30)
                    for n, c in [('L_mean_s', 'L_s'), ('S_mean_s', 'S_s')])
        passed = check['gate']['pass_gate'] and error <= .01
        checked.append(dict(point_id=row['point_id'], passed=passed, max_relative_error=error,
                            raw=check['raw'], raw_sha256=check['raw_sha256']))
        if not passed:
            rejected.add(row['point_id'])
    write_csv(out / 'candidate_points.csv', points)
    write_csv(out / 'configurations.csv', configs)
    write_csv(out / 'frontier_checks960.csv', checked)
    write_csv(out / 'box_comparisons.csv', comparisons)
    write_csv(out / 'frontier_points.csv', fronts)
    counts = {}
    for r in comparisons:
        key = '|'.join(r[k] for k in ('eligibility', 'dimensions', 'baseline', 'alternative'))
        counts.setdefault(key, Counter())[r['relation']] += 1
    report = dict(hardware_identities=len(templates), configurations=len(configs), candidates=len(points),
        unique_semantics=sum(s['semantics'] for s in shards), shards=shards,
        frontier_identity_checks=len(checked), unique_checks960=len(checks),
        failed_checks=sorted(rejected), counts=counts, incumbent_pruning=False,
        max_relative_error=max((c['max_relative_error'] for c in checked), default=0),
        scope='All V7-retained hardware identities; all VLM splits; five pipeline organizations plus serial; '
              'five Tmin-relative periods; original model/calibration assumptions; not continuous global optimization.',
        task_episodes=0, publishable=not rejected,
        source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==manifest[str(source.relative_to(ROOT))])
    write_json(out / 'summary.json', report)
    print(json.dumps(report, indent=2), flush=True)
    if rejected:
        raise RuntimeError('Frontier checks failed; do not publish these frontiers')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'results/v9_no_batching_domain')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    run(args.out.resolve(), args.workers)
