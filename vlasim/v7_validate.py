"""Selected-point 960-request checks and matched empirical stress scenarios."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import itertools
from pathlib import Path
import subprocess
import sys

import numpy as np

from v7_common import (ROOT, V6, candidates, read_csv, write_csv, write_json, load, digest,
                       token, checkpoint, truth, feasible)
from v7_figdata import ablation_rows
from v6_band import engine_from_row
from v51_dse import semantic_key, summarize
from v4_scheduler import periodic_gate

COLS = ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s')
ROUND_COLS = ('start_s', 'end_s', 'duration_s', 'compute_s', 'exposed_memory_s',
              'linear_s', 'attention_s', 'dram_bytes', 'weight_bytes', 'wait_before_s',
              'stage_mask', 'tail_drain')


def library():
    out = ROOT / 'validation'
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('periodic.dylib' if sys.platform == 'darwin' else 'periodic.so')
    if not target.exists():
        subprocess.run(['c++', '-O2', '-ffp-contract=off', '-std=c++17', '-shared', '-fPIC',
                        'vlasim/v6_periodic.cpp', '-o', str(target)], check=True)
    return target


def accounting(result, engine):
    rounds = result['dit_rounds']
    worst = 0.
    for r in rounds:
        for total in (r['compute_s'] + r['exposed_memory_s'], r['linear_s'] + r['attention_s']):
            worst = max(worst, abs(r['duration_s'] - total))
        if worst > 1e-8:
            raise RuntimeError('HARD_STOP_round_time_conservation')
        mask = r['stage_mask']
        expected = sum(engine.d[i].bytes for i in range(engine.offsets[mask],
                         engine.offsets[mask] + engine.lengths[mask]))
        if abs(expected - r['dram_bytes']) > max(1., expected * 1e-10):
            raise RuntimeError('HARD_STOP_round_traffic_accounting')
    n = len(result['requests'])
    dit = sum(r['dram_bytes'] for r in rounds) / n / 1e9
    vlm = sum(op.bytes for op in engine.v) / 1e9
    if abs(dit - result['dit_GB_per_req']) > 1e-8 or abs(dit + vlm - result['dram_GB_per_req']) > 1e-8:
        raise RuntimeError('HARD_STOP_total_traffic_accounting')
    return dict(passed=True, max_round_time_error_s=worst, reconciled_dit_GB_per_req=dit)


def engine_identity(row):
    fields = ('hardware_id', 'config_id', 'mode', 'vlm_cores', 'dit_stages', 'dit_batching',
              'model', 'track', 'bw_policy', 'bg', 'max_wait', 'stream_partition', 'dit_resident_mb',
              'kv_on_chip', 'vlm_util', 'vlm_queue_max')
    return tuple(row.get(k) for k in fields)


def plan(phase='pre_recheck'):
    base = ROOT / ('paper/pre_recheck' if phase == 'pre_recheck' else 'paper')
    rows = {r['point_id']: r for r in candidates()}
    required, reference = set(), set()
    for r in read_csv(base / 'pareto_frontier_points.csv'):
        required.add(r['point_id'])
        reference.add(r['point_id'])
    for r in read_csv(base / 'F3_all_feasible_points.csv'):
        required.add(r['point_id'])
    for r in read_csv(base / 'global_area_selected_points.csv'):
        required.add(r['point_id'])
        reference.add(r['point_id'])
    for r in ablation_rows():
        rows[r['point_id']] = r
        required.add(r['point_id'])
        reference.add(r['point_id'])
    selected = [dict(rows[key], independent_python_reference=key in reference) for key in sorted(required)]
    write_csv(ROOT / 'validation/recheck_plan.csv', selected)
    write_json(ROOT / 'validation/recheck_plan_status.json', dict(phase=phase,
        points=len(selected), python_reference_points=len(reference), requests=960, warmup=192,
        scope='All frontier identities, all F2 controls, all feasible F3 curve identities, plus global-area choices. '
              'All checked at960 with compiled kernel; frontier/F2/area choices additionally compared to Python reference. '
              'Exact operation-template/period equivalences share raw runs.'))
    return selected


def recheck_shard(task):
    memory, cores = task
    rows = [r for r in read_csv(ROOT / 'validation/recheck_plan.csv')
            if r['memory'] == memory and int(r['n_cores']) == cores]
    out = ROOT / 'validation/rechecks' / f'{memory}_c{cores}'
    out.mkdir(parents=True, exist_ok=True)
    cal = load(ROOT / 'inputs/calibration.json')
    lib = library()
    engines = {}
    runs = {}
    references = {}
    results = []
    identity = token(dict(rows=rows, source=digest(__file__), calibration=digest(ROOT / 'inputs/calibration.json'),
                          library_source=digest('vlasim/v6_periodic.cpp')))
    saved = checkpoint(out / 'status.json', identity)
    if saved:
        return saved
    for row in rows:
        ekey = engine_identity(row)
        if ekey not in engines:
            engines[ekey] = engine_from_row(row, lib, calibrations=cal)
        engine = engines[ekey]
        period = float(row['T_s'])
        runkey = token((semantic_key(engine), period, engine.reference.sram_ok))
        target = out / (runkey + '.json')
        if runkey not in runs:
            if target.exists():
                value = load(target)
                if digest(out / value['raw']) != value['raw_sha256']:
                    raise RuntimeError('HARD_STOP_recheck_raw_hash')
            else:
                result = engine.run(period, 960, 192)
                check = accounting(result, engine)
                metrics = summarize(result, period, engine.k)
                raw = runkey + '.npz'
                np.savez_compressed(out / raw,
                    requests=np.array([[r[k] for k in COLS] for r in result['requests']]),
                    rounds=np.array([[r[k] for k in ROUND_COLS] for r in result['dit_rounds']]))
                value = dict(**metrics, accounting=check, raw=raw, raw_sha256=digest(out / raw))
                write_json(target, value)
            runs[runkey] = value
        value = runs[runkey]
        gate = value['gate']
        reference_error = None
        if truth(row['independent_python_reference']):
            refpath = out / (runkey + '.python.json')
            if runkey not in references:
                if refpath.exists():
                    ref = load(refpath)
                    if digest(out / ref['raw']) != ref['raw_sha256']:
                        raise RuntimeError('HARD_STOP_Python_reference_hash')
                else:
                    engine.reference.mp = replace(engine.reference.mp, launch_period_s=period)
                    original = engine.reference.run(960, 192, diagnostics=True)
                    array = np.array([[r[k] for k in COLS] for r in original['requests']])
                    with np.load(out / value['raw']) as data:
                        error = float(np.max(np.abs(array - data['requests'])))
                    if error > 1e-6:
                        raise RuntimeError('HARD_STOP_compiled_Python_timestamp_difference')
                    raw = runkey + '.python.npz'
                    np.savez_compressed(out / raw, requests=array)
                    ref = dict(gate=periodic_gate(original, period, engine.k), error_s=error,
                               raw=raw, raw_sha256=digest(out / raw))
                    write_json(refpath, ref)
                references[runkey] = ref
            ref = references[runkey]
            reference_error = ref['error_s']
            gate = ref['gate']
        errors = [abs(gate[key] - float(row[col])) / max(abs(float(row[col])), 1e-30)
                  for key, col in (('L_mean_s', 'L_s'), ('S_mean_s', 'S_s'))]
        passed = gate['pass_gate'] and max(errors) <= .01 and engine.reference.sram_ok
        results.append(dict(point_id=row['point_id'], hardware_id=row['hardware_id'],
            memory=memory, run_key=runkey, raw=str(out / value['raw']),
            gate_passed=gate['pass_gate'], recheck_passed=passed,
            nominal_L_s=float(row['L_s']), nominal_S_s=float(row['S_s']),
            L_960_s=gate['L_mean_s'], S_960_s=gate['S_mean_s'],
            L_relative_error=errors[0], S_relative_error=errors[1],
            python_reference_requested=truth(row['independent_python_reference']),
            python_max_absolute_error_s=reference_error,
            accounting_passed=value['accounting']['passed'],
            max_round_time_error_s=value['accounting']['max_round_time_error_s'],
            comparison_scope='960 consistency check; not new independent DRAM heldout validation'))
    write_csv(out / 'points.csv', results)
    status = dict(identity=identity, points=len(rows), unique_fast_runs=len(runs),
                  unique_python_reference_runs=len(references),
                  hashes={p.name: digest(p) for p in out.iterdir() if p.is_file() and p.name != 'status.json'})
    write_json(out / 'status.json', status)
    print('Rechecked', memory, cores, len(rows), 'identities', len(runs), 'runs', flush=True)
    return status


def recheck(workers=4, phase='pre_recheck'):
    selected = plan(phase)
    library()
    keys = sorted({(r['memory'], int(r['n_cores'])) for r in selected})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        statuses = [f.result() for f in as_completed([pool.submit(recheck_shard, k) for k in keys])]
    results = [r for k in keys for r in read_csv(ROOT / 'validation/rechecks' / f'{k[0]}_c{k[1]}/points.csv')]
    write_csv(ROOT / 'validation/recheck_results.csv', results)
    write_json(ROOT / 'validation/recheck_summary.json', dict(points=len(results),
        passed=sum(truth(r['recheck_passed']) for r in results),
        excluded_point_ids=[r['point_id'] for r in results if not truth(r['recheck_passed'])],
        unique_fast_runs=sum(s['unique_fast_runs'] for s in statuses),
        unique_python_reference_runs=sum(s['unique_python_reference_runs'] for s in statuses),
        max_L_relative_error=max(float(r['L_relative_error']) for r in results),
        max_S_relative_error=max(float(r['S_relative_error']) for r in results),
        max_python_absolute_error_s=max(float(r['python_max_absolute_error_s']) for r in results
                                      if r['python_max_absolute_error_s']),
        traffic_accounting_passed=all(truth(r['accounting_passed']) for r in results),
        new_cross_host_comparison=False,
        cross_host_scope='Frozen V5.1 cross-host controls retained; no new remote run claimed.',
        policy='Failing960 gates or >1% L/S changes excluded, failures retained; nominal values never silently replaced.'))


def scenarios(standard):
    q = load(ROOT / 'inputs/band/quantiles.json')['groups']
    for window in ('W1', 'W3', 'W4', 'W5'):
        v = q.get('/'.join((standard, window, 'vlm')))
        d = q.get('/'.join((standard, window, 'dit')))
        if v is None and d is None:
            continue
        for vp, dp in itertools.product(('p5', 'p50', 'p95') if v else ('unmeasured_unchanged',),
                                       ('p5', 'p50', 'p95') if d else ('unmeasured_unchanged',)):
            yield window, vp, dp, (1/(1+v[vp]) if v else 1., 1/(1+d[dp]) if d else 1.)


def stress_shard(task):
    memory, cores = task
    planrows = read_csv(ROOT / 'validation/stress_plan.csv')
    rows = [r for r in planrows if r['memory'] == memory and int(r['n_cores']) == cores]
    out = ROOT / 'validation/stress' / f'{memory}_c{cores}'
    out.mkdir(parents=True, exist_ok=True)
    identity = token((rows, digest(__file__), digest(ROOT / 'inputs/band/quantiles.json')))
    saved = checkpoint(out / 'status.json', identity)
    if saved:
        return saved
    cal = load(ROOT / 'inputs/calibration.json')
    lib = library()
    cache = {}
    results = []
    for row in rows:
        for window, vp, dp, scales in scenarios(memory.split('_')[0]):
            engine = engine_from_row(row, lib, scales, cal)
            period = float(row['T_s'])
            key = token((semantic_key(engine), period, scales))
            if key not in cache:
                path = out / (key + '.json')
                if path.exists():
                    value = load(path)
                    if digest(out / value['raw']) != value['raw_sha256']:
                        raise RuntimeError('HARD_STOP_stress_raw_hash')
                else:
                    result = engine.run(period, 960, 192)
                    check = accounting(result, engine)
                    gate = periodic_gate(result, period, engine.k)
                    raw = key + '.npz'
                    np.savez_compressed(out / raw, requests=np.array([[r[k] for k in COLS] for r in result['requests']]))
                    value = dict(gate=gate, accounting=check, raw=raw, raw_sha256=digest(out / raw))
                    write_json(path, value)
                cache[key] = value
            value = cache[key]
            results.append(dict(point_id=row['point_id'], memory=memory, window=window,
                vlm_quantile=vp, dit_quantile=dp, vlm_scale=scales[0], dit_scale=scales[1],
                gate_passed=value['gate']['pass_gate'], L_s=value['gate']['L_mean_s'],
                S_s=value['gate']['S_mean_s'], raw=str(out / value['raw']),
                accounting_passed=value['accounting']['passed'],
                transfer_status='old_residuals_transferred_UNVALIDATED_new_identity' if row['evidence_root'] == str(V6)
                    else 'empirical_stress_not_probability_or_CI'))
    write_csv(out / 'runs.csv', results)
    status = dict(identity=identity, points=len(rows), scenarios=len(results), unique_runs=len(cache),
                  hashes={p.name: digest(p) for p in out.iterdir() if p.is_file() and p.name != 'status.json'})
    write_json(out / 'status.json', status)
    print('Stressed', memory, cores, len(rows), len(cache), 'unique scenarios', flush=True)
    return status


def stress(workers=4):
    pairs = read_csv(ROOT / 'paper/strictly_dominating_pairs.csv')
    required = {r[k] for r in pairs for k in ('task_point_id', 'lat_point_id')}
    selected = [r for r in candidates() if r['point_id'] in required]
    write_csv(ROOT / 'validation/stress_plan.csv', selected)
    keys = sorted({(r['memory'], int(r['n_cores'])) for r in selected})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        statuses = [f.result() for f in as_completed([pool.submit(stress_shard, k) for k in keys])]
    runs = [r for k in keys for r in read_csv(ROOT / 'validation/stress' / f'{k[0]}_c{k[1]}/runs.csv')]
    write_csv(ROOT / 'validation/stress_runs.csv', runs)
    lookup = {}
    for r in runs:
        lookup.setdefault(r['point_id'], {})[r['window'], r['vlm_quantile'], r['dit_quantile']] = r
    pair_results = []
    point_results = {}
    for pair in pairs:
        a, b = pair['lat_point_id'], pair['task_point_id']
        matched = set(lookup[a]) & set(lookup[b])
        na = nb = nj = 0
        for key in matched:
            x, y = lookup[a][key], lookup[b][key]
            ok_a = truth(x['gate_passed']) and feasible(dict(x, mode='serial'),
                float(pair['Lmax_ms']), float(pair['Smax_ms']), 'latency_only')
            ok_b = truth(y['gate_passed']) and feasible(y,
                float(pair['Lmax_ms']), float(pair['Smax_ms']), 'task_aware')
            na += ok_a
            nb += ok_b
            nj += ok_a and ok_b
        n = len(matched)
        pair_results.append(dict(pair, scenarios=n, lat_feasible_fraction=na/n,
            task_feasible_fraction=nb/n, joint_feasible_fraction=nj/n,
            task_robust_at_80pct=nb/n >= .8, pair_robust_at_80pct=nj/n >= .8,
            scope='fixed nominal resource dominance; empirical matched scenarios, not probabilities'))
        identity = (pair['Lmax_ms'], pair['Smax_ms'], b)
        point_results[identity] = dict(Lmax_ms=pair['Lmax_ms'], Smax_ms=pair['Smax_ms'],
            task_point_id=b, feasible_fraction=nb/n, robust_at_80pct=nb/n >= .8, scenarios=n)
    write_csv(ROOT / 'paper/strict_pair_stress.csv', pair_results)
    write_csv(ROOT / 'paper/strict_task_point_stress.csv', point_results.values())
    write_json(ROOT / 'validation/stress_summary.json', dict(points=len(selected),
        scenario_rows=len(runs), unique_runs=sum(r['unique_runs'] for r in statuses),
        stable_scenarios=sum(truth(r['gate_passed']) for r in runs), pairs=len(pair_results),
        strict_task_box_points=len(point_results),
        strict_task_box_points_robust80=sum(r['robust_at_80pct'] for r in point_results.values()),
        strict_pairs_robust80=sum(r['pair_robust_at_80pct'] for r in pair_results),
        new_heldout_executed=False, empirical_quantiles_not_CI=True,
        W1_DiT_scope='unmeasured, unchanged', resource_dominance_does_not_change_under_bandwidth_stress=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('recheck', 'stress'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--phase', default='pre_recheck')
    args = parser.parse_args()
    recheck(args.workers, args.phase) if args.action == 'recheck' else stress(args.workers)
