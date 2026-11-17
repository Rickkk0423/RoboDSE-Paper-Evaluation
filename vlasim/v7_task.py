"""At-most16 honest task measurements, including low-L controls and counterexamples."""
from dataclasses import replace
from pathlib import Path
import numpy as np

from v7_common import (ROOT, candidates, resource, summary, read_csv, write_csv,
                       write_json, load, digest, token, truth)
from v7_validate import library, accounting, COLS
from v6_band import engine_from_row
from v4_scheduler import periodic_gate


def rank(row):
    return (resource(row, True)[2], float(row['local_kb']), round(float(row['L_s']), 9),
            float(row['S_s']), row['point_id'])


def select():
    excluded = set(load(ROOT / 'validation/recheck_summary.json')['excluded_point_ids'])
    points = [r for r in candidates() if r['point_id'] not in excluded]
    lookup = {r['point_id']: r for r in points}
    pairs = read_csv(ROOT / 'paper/strictly_dominating_pairs.csv')
    fronts = read_csv(ROOT / 'paper/pareto_frontier_points.csv')
    picked = {}
    def add(row, priority, claim):
        if row['point_id'] in picked:
            return False
        picked[row['point_id']] = dict(row, measurement_priority=priority,
                                      supported_claim=claim)
        return True
    # Reserve six slots for four distinct low-L references and two counterexamples.
    main = [p for p in pairs if (int(p['Lmax_ms']), int(p['Smax_ms'])) in ((200, 100), (250, 150))]
    for pair in sorted(main, key=lambda p: (float(p['bandwidth_ratio']), float(p['core_ratio']))):
        missing = [lookup[pair[k]] for k in ('lat_point_id', 'task_point_id') if pair[k] not in picked]
        if len(picked) + len(missing) <= 10:
            for r in missing:
                add(r, 1, 'Test strict resource dominance for the main Box; timing feasibility is not task success.')
    representatives = {}
    for p in pairs:
        r = lookup[p['task_point_id']]
        key = r['memory'], int(r['n_cores']), int(r['dit_stages']), truth(r['dit_batching'])
        if key not in representatives or rank(r) < rank(representatives[key]):
            representatives[key] = r
    other_candidates = sorted(representatives.values(), key=lambda r: (resource(r), rank(r)))
    for r in other_candidates[:4]:
        if len(picked) < 10:
            add(r, 2, 'Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet.')
    # The actual main Boxes have no strict pairs: label resource tradeoffs honestly.
    for box in ((200, 100), (250, 150)):
        representatives = {}
        for f in fronts:
            if (int(f['Lmax_ms']), int(f['Smax_ms'])) != box:
                continue
            r = lookup[f['point_id']]
            key = f['protocol'], resource(r)
            if key not in representatives or rank(r) < rank(representatives[key]):
                representatives[key] = r
        for (protocol, vector), r in sorted(representatives.items()):
            if len(picked) < 10:
                add(r, 2, f'Box{box}: test {protocol} resource alternative {vector}; '
                    'extension or equality is not strict resource improvement.')
    for r in other_candidates:
        if len(picked) < 10:
            add(r, 2, 'Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet.')
    low = [r for r in points if float(r['L_s']) < .1]
    low_added = 0
    for target in (.025, .05, .075, .095):
        r = min((r for r in low if r['point_id'] not in picked),
                key=lambda r: (abs(float(r['L_s']) - target), resource(r, True), r['point_id']))
        add(r, 3, f'Low-latency reference near{target*1000:g}ms to locate the left boundary of a task-performance plateau.')
        low_added += 1
    outside = [r for r in points if float(r['L_s']) > .3 or float(r['S_s']) > .15]
    preferred = [r for r in outside if r['memory'] == 'LPDDR5_c4' and int(r['n_cores']) == 3
                 and r['mode'] == 'pipelined' and int(r['dit_stages']) == 2 and truth(r['dit_batching'])]
    first = min(preferred or outside, key=lambda r: (abs(float(r['L_s'])-.338) + abs(float(r['S_s'])-.169), rank(r)))
    add(first, 4, 'Outside-platform counterexample near338/169ms: test whether optimistic platform extrapolation fails.')
    second = min((r for r in outside if r['point_id'] not in picked and float(r['L_s']) > .3),
                 key=lambda r: (abs(float(r['L_s'])-.45) + abs(float(r['S_s'])-.225), rank(r)))
    add(second, 4, 'Second outside-platform counterexample: task quality must not be inferred from timing alone.')
    while len(picked) < 16:
        r = min((r for r in points if r['point_id'] not in picked),
                key=lambda r: (abs(float(r['L_s'])-.15), rank(r)))
        add(r, 5, 'Intermediate latency control to test the shape between low-L references and outside-platform examples.')
    selected = list(picked.values())
    if len(selected) > 16 or low_added != 4 or sum(r['measurement_priority'] == 4 for r in selected) < 2:
        raise RuntimeError('Task measurement budget/coverage failure')
    return selected, len(main)


def run():
    out = ROOT / 'task'
    out.mkdir(parents=True, exist_ok=True)
    selected, main_pairs = select()
    cal = load(ROOT / 'inputs/calibration.json')
    lib = library()
    audits = []
    for row in selected:
        directory = out / 'timing_rechecks' / row['point_id']
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'status.json'
        identity = token((row, digest(__file__), digest(ROOT / 'inputs/calibration.json')))
        if path.exists():
            status = load(path)
            if status['identity'] != identity or digest(directory / 'requests.npz') != status['raw_sha256']:
                raise RuntimeError('Task timing checkpoint changed')
        else:
            engine = engine_from_row(row, lib, calibrations=cal)
            period = float(row['T_s'])
            result = engine.run(period, 960, 192)
            account = accounting(result, engine)
            engine.reference.mp = replace(engine.reference.mp, launch_period_s=period)
            original = engine.reference.run(960, 192, diagnostics=True)
            a = np.array([[r[k] for k in COLS] for r in result['requests']])
            b = np.array([[r[k] for k in COLS] for r in original['requests']])
            error = float(np.max(np.abs(a-b)))
            if error > 1e-6:
                raise RuntimeError('HARD_STOP_task_Python_compiled_difference')
            gate = periodic_gate(original, period, engine.k)
            relative = max(abs(gate[key]-float(row[col]))/float(row[col])
                           for key, col in (('L_mean_s', 'L_s'), ('S_mean_s', 'S_s')))
            np.savez_compressed(directory / 'requests.npz', fast=a, original=b)
            status = dict(identity=identity, point_id=row['point_id'], gate=gate,
                passed=gate['pass_gate'] and relative <= .01, relative_error=relative,
                python_compiled_error_s=error, accounting=account,
                raw_sha256=digest(directory / 'requests.npz'))
            write_json(path, status)
        audits.append(status)
    if not all(r['passed'] for r in audits):
        write_json(out / 'timing_failure.json', dict(audits=audits))
        raise RuntimeError('Task proposal960 timing failure; evidence retained')
    output = [dict(**summary(r), priority=r['measurement_priority'], supported_claim=r['supported_claim'],
                   L_960_ms=next(a['gate']['L_mean_s']*1000 for a in audits if a['point_id'] == r['point_id']),
                   S_960_ms=next(a['gate']['S_mean_s']*1000 for a in audits if a['point_id'] == r['point_id'])) for r in selected]
    write_csv(out / 'selected_points.csv', output)
    lines = ['# V7 Task Measurement Request', '',
        'Exactly16 proposed timing points; zero closed-loop task episodes were run.',
        'The two main Boxes have no strict resource-dominating pairs. Their rows test actual resource alternatives, not a nonexistent dominance claim.', '',
        '| Point | Hardware | Mapping | L/S(ms),960 | Priority | Supported Claim |',
        '| --- | --- | --- | --- | --- | --- |']
    for r in output:
        mapping = r['mode'] + '/k' + str(r['k']) + (' batched' if r['batching'] else ' unbatched')
        lines.append(f'| {r["point_id"]} | {r["hardware_id"]} | {mapping} | '
                     f'{r["L_960_ms"]:.3f}/{r["S_960_ms"]:.3f} | {r["priority"]} | {r["supported_claim"]} |')
    lines += ['', '## Required External Protocol Inputs', '',
        'Environment/version, policy checkpoint, speed bands, trial budgets, random seeds, latency injection, action chunk rules and episode deadlines remain null until the author supplies them.',
        'Record every episode, including invalid episodes, with exact point_id, environment/checkpoint hashes, seed, L/S injection, wall time, success, invalid flag and invalid reason.',
        'Report both protocols: invalid-as-failure uses all attempted episodes as denominator; invalid-excluded uses valid episodes only. If all attempts are invalid, invalid-excluded success rate is null, never zero.',
        'No guessed checkpoints, fabricated episodes, inferred success rates or unexecuted speed bands may appear as results.',
        'Use the unchanged V6 real-result validator only after genuine records are supplied: '
        '`PYTHONPATH=vlasim .venv/bin/python vlasim/v6_task.py validate --input <real_records.json> --output <new_validation.json>`.',
        'Timing checks here are simulator rechecks, not closed-loop task evaluation.']
    (out / 'measurement_request_v7.md').write_text('\n'.join(lines)+'\n')
    write_json(out / 'status.json', dict(points=len(output), maximum=16, low_latency_references=4,
        outside_platform_counterexamples=2, main_Box_strict_pairs=main_pairs,
        timing960_passed=sum(r['passed'] for r in audits), task_episodes_run=0,
        external_protocol_inputs=dict(environment=None, checkpoint=None, speed_bands=None,
                                      trial_budgets=None, latency_injection=None, chunk_rules=None)))
    print('Prepared16 task points;16 timing checks passed;0 task episodes', flush=True)


if __name__ == '__main__':
    run()
