"""Audited resource-first tables; timing constraints are not empirical SR targets."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

from report_dynamicvla_pilot import table

ROOT = Path(__file__).resolve().parents[1]
BOXES = ((160, 80), (200, 100), (240, 120), (300, 160), (300, 240))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed(row, arm):
    return arm == 'full' or row['mode'] == 'serial' or (
        arm == 'no_batching' and (int(row['k']) == 1 or row['batching'] == 'False'))


def resource(row):
    return (int(row['total_MACs']), int(row['cores']), float(row['sram_mb']), float(row['peak_GBps']))


def frontiers(rows):
    vectors = set(map(resource, rows))
    return sorted(v for v in vectors if not any(w != v and all(x <= y for x, y in zip(w, v)) for w in vectors))


def pretty(row):
    return [f'{row["cores"]} x {row["array_dim"]}x{row["array_dim"]}',
            f'{float(row["peak_GBps"]):g}', f'{float(row["sram_mb"]):g}',
            'serial' if row['mode'] == 'serial' else f'V{row["vlm_cores"]}/k{row["k"]}/'+('batch' if row['batching'] == 'True' else 'no-batch'),
            f'{float(row["L_ms"]):.2f}', f'{float(row["S_ms"]):.2f}']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.root/'manifest.json').read_text())
    summary = json.loads((a.root/'summary.json').read_text())
    assert digest(ROOT/'publication/dynamicvla_pilot/profile.json') == manifest['profile_sha256']
    calibration_source = Path(manifest.get('calibration_source', ROOT/'results/v7/inputs/calibration.json'))
    if not calibration_source.is_absolute():
        calibration_source = ROOT / calibration_source
    assert digest(calibration_source) == manifest['calibration_sha256']
    for name, sha in manifest['sources'].items():
        assert digest(ROOT/name) == sha, name
    verified = 0
    for path in (a.root/'runs').glob('*/status.json'):
        status = json.loads(path.read_text())
        assert digest(path.parent/'requests.npz') == status['raw_sha256']
        check = json.loads((path.parent/'check960.json').read_text())
        assert digest(path.parent/'check960.npz') == check['raw_sha256']
        assert check['gate']['pass_gate'] and check['max_relative_error'] < .01
        verified += 1
    assert verified == summary['unique_960_runs']
    with (a.root/'candidate_points.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    minimum = [r for r in rows if float(r['factor']) == 1]
    for r in rows:
        assert int(r['total_MACs']) == int(r['array_dim'])**2*int(r['cores'])
        assert float(r['peak_TFLOPs']) == int(r['total_MACs'])*.002
    bounds = []
    # Anchor and low-bandwidth sensitivity are always selected separately.
    calibrated_scope = summary.get('calibration_scope', manifest.get('calibration_scope'))
    scopes = ('inherited_fit_anchor', 'uncalibrated_peak_sensitivity')
    if calibrated_scope and calibrated_scope not in scopes:
        scopes = (calibrated_scope, 'uncalibrated_peak_sensitivity')
    for scope in scopes:
        for l, s in BOXES:
            for arm in ('serial', 'no_batching', 'full'):
                pool = [r for r in rows if r['memory_scope'] == scope and allowed(r, arm)
                        and float(r['L_ms']) <= l and float(r['S_ms']) <= s]
                vectors = frontiers(pool)
                reps = []
                for v in vectors:
                    same = [r for r in pool if resource(r) == v]
                    # A diagnostic witness, not a task-success optimizer.
                    reps.append(min(same, key=lambda r: (float(r['L_ms']), float(r['S_ms']))))
                bounds.append(dict(scope=scope, Lmax_ms=l, Smax_ms=s, arm=arm,
                                   feasible_points=len(pool), vectors=vectors, witnesses=reps))
    anchor_scope = calibrated_scope or 'inherited_fit_anchor'
    anchor_serial = [r for r in minimum if r['mode'] == 'serial' and float(r['sram_mb']) == 8
                     and r['memory_scope'] == anchor_scope]
    serial_table = [pretty(r)+[f'{float(r["peak_TFLOPs"]):.3f}',
                              f'{100*float(r["useful_throughput_fraction"]):.1f}%'] for r in anchor_serial]
    controls = [r for r in minimum if int(r['array_dim']) == 32 and int(r['cores']) == 2
                and float(r['sram_mb']) == 8 and r['memory_scope'] == 'inherited_fit_anchor']
    targets = []
    for b in bounds:
        if b['arm'] != 'full' or not b['witnesses']:
            continue
        chosen = min(b['witnesses'], key=lambda r: (int(r['total_MACs']), float(r['sram_mb']),
                                                   float(r['peak_GBps']), int(r['cores']), float(r['L_ms'])))
        targets.append([b['scope'], f'{b["Lmax_ms"]}/{b["Smax_ms"]}']+pretty(chosen)+[chosen['total_MACs']])
    # Prefer informative matched-hardware examples within the explored latency range.
    successes = []
    for r in minimum:
        if r['mode'] != 'pipelined' or r['batching'] != 'True' or int(r['k']) < 2:
            continue
        if not (100 <= float(r['L_ms']) <= 300):
            continue
        same = [q for q in minimum if resource(q) == resource(r) and q['mode'] == 'serial']
        baseline = min(same, key=lambda q: float(q['L_ms']))
        improvement = 1-float(r['S_ms'])/float(baseline['S_ms'])
        if improvement > .1:
            successes.append(dict(point=r, serial=baseline, refresh_reduction_pct=improvement*100))
    examples = []
    for scope in ('inherited_fit_anchor', 'uncalibrated_peak_sensitivity'):
        pool = [v for v in successes if v['point']['memory_scope'] == scope]
        if pool:
            examples.append(min(pool, key=lambda v: (int(v['point']['total_MACs']),
                                                      float(v['point']['sram_mb']), -v['refresh_reduction_pct'])))
    a.out.mkdir(parents=True, exist_ok=True)
    for file in ('summary.json', 'manifest.json', 'candidate_points.csv', 'configurations.csv',
                 'checks960.csv', 'reference_checks.json'):
        shutil.copy2(a.root/file, a.out/file)
    (a.out/'resource_frontiers.json').write_text(json.dumps(bounds, indent=2)+'\n')
    (a.out/'matched_hardware_examples.json').write_text(json.dumps(examples, indent=2)+'\n')
    (a.out/'verification.json').write_text(json.dumps(dict(passed=True, verified_runs=verified,
        physical_validation=False, task_episodes=0), indent=2)+'\n')
    example_tables = []
    for example in examples:
        r = example['point']
        same = [q for q in minimum if resource(q) == resource(r) and
                (q['mode'] == 'serial' or q['vlm_cores'] == r['vlm_cores'])]
        example_tables.append('### '+r['memory_scope']+'\n\n'+table(
            ['Hardware','BW GB/s','SRAM MB','Mapping','L ms','S ms','DiT GB/req'],
            [pretty(q)+[f'{float(q["steady_dit_GB_per_req"]):.3f}'] for q in same]))
    text = f'''# DynamicVLA Resource-First Small-Array Sweep

Date: 2026-11-18. Exploratory modeled hardware timing only. The successful fixed-input DynamicVLA trace from the previous pilot is reused unchanged. This delivery records the calibration scope in the manifest; it does not claim closed-loop task success.

## Search Objective

Seek smaller hardware meeting relaxed L/S upper bounds, not the lowest possible latency. We do not add artificial delay, lower the clock, or discard faster candidates just to force L into 100-300 ms. That range is an exploratory focus, not an empirically measured success contour.

All cores run at 1 GHz. The array choices are:

| Array per core | MAC units per core | Peak TFLOP/s per core | MAC units relative to 128x128 |
| --- | --- | --- | --- |
| 16x16 | 256 | 0.512 | 1/64 |
| 32x32 | 1024 | 2.048 | 1/16 |
| 64x64 | 4096 | 8.192 | 1/4 |
| 128x128 (previous pilot) | 16384 | 32.768 | 1 |

The sweep uses 1/2/4 cores, 4/8/32 MB shared SRAM, and 32 KB private SRAM per core. Private SRAM passes the existing static double-buffer tile feasibility test, but its capacity-dependent performance is NOT modeled. Reduction in MAC units or SRAM is not a measured die-area/power reduction.

Calibration scope: `{summary.get('calibration_model', manifest.get('calibration_model', 'pi05'))}` / `{summary.get('calibration_scope', manifest.get('calibration_scope', 'unspecified'))}`. The calibrated DynamicVLA run uses the independent calibration JSON recorded in the manifest. Peak-bandwidth points outside the native calibration geometry remain sensitivity points, not calibrated physical channels.

## Completed Work

- {summary['hardware_identities']} hardware identities; {summary['configurations']} execution configurations; {summary['candidate_points']} retained timing points.
- All serial and valid VLM/DiT splits, k=1, k=2/3 with and without batching.
- Minimum stable periods searched with 480 requests/96 warmup, followed by {summary['checks960']} configuration-level 960-request/192-warmup checks ({verified} unique semantics).
- Maximum 480/960 relative difference: {summary['max_relative_error']:.3e}.
- {summary['python_cpp_checks']} Python/C++ comparisons cover every array size and execution organization; maximum absolute difference {summary['max_python_cpp_abs_error']:.3e}.
- Raw evidence and source hashes checked. These checks establish internal consistency, not physical timing accuracy.

## Fewer MAC Units, Useful Latency Range

Serial operation, 8 MB shared SRAM and 51.2 GB/s:

{table(['Hardware','BW GB/s','SRAM MB','Mapping','L ms','S ms','Peak TFLOP/s','Useful throughput / peak'], serial_table)}

The last column is modeled useful FLOP/request divided by S and peak FLOP/s. It is not a measured array occupancy, active-cycle fraction or energy efficiency. Missing non-matmul costs and analytical convolution timing limit its accuracy.

## When Batching Does Not Help

Fixed two 32x32 cores, 8 MB SRAM, 51.2 GB/s; pipelined rows use one core per group:

{table(['Hardware','BW GB/s','SRAM MB','Mapping','L ms','S ms'], [pretty(r) for r in controls])}

With tiny compute groups, prefix execution can dominate. A hard VLM/DiT split then leaves insufficient prefix compute; sharing DiT weights does not remove that bottleneck. Serial remains in the full search and can win. A one-core time-multiplexed batching implementation is not represented by the current scheduler.

## Matched-Hardware Batching Examples

Examples below are selected within modeled L=100-300 ms and require a refresh reduction greater than 10% versus the same-hardware minimum-period serial point. Selection prioritizes fewer MAC units, then smaller SRAM. They are diagnostics, not unbiased aggregate task gains.

{chr(10).join(example_tables) if examples else 'No qualifying example in this sweep.'}

## Resource-First Selection

The resource vector is (total MAC units, core count, shared SRAM, peak BW). Private SRAM is 32 KB per core throughout. Anchor and low-bandwidth sensitivity candidates are never mixed in one frontier. All timing-curve factors are considered, including points faster than 100 ms.

Below is one minimum-MAC witness per box, with ties broken by shared SRAM, BW, core count and then L. Full Pareto sets and witness identities are in `resource_frontiers.json`; these are not global area minima.

{table(['Evidence scope','Box L/S ms','Hardware','BW GB/s','SRAM MB','Mapping','L ms','S ms','Total MACs'], targets)}

## Limits and Next Step

1. This establishes that a smaller-array search is useful; it does not establish a final minimum-cost chip or measured task success.
2. Keep serial/no-batching/batching alternatives. Smaller arrays can make computation dominant and reduce or reverse the value of cross-chunk batching.
3. BF16 target arithmetic is assumed although the source model is mixed FP32/BF16. Convolution uses an analytical compute floor; normalization, softmax and other non-matmul work are omitted. Small-array conclusions need convolution/tiling validation in particular.
4. SRAM working sets and traffic are approximate. The change from 512 KB to 32 KB private SRAM is checked only for static tile fit, not compiled buffering/tiling or runtime performance.
5. The native calibration itself uses the pinned HBM2 eight-channel Ramulator geometry; the 12.8/25.6/51.2 GB/s sweep is still a peak-bandwidth sensitivity study unless separately calibrated. Validate DiT batching numerically before robotic SR rollouts. Preserve the 40 ms control-step protocol and report any timing quantization explicitly.
6. Use timing boxes to shortlist designs; do not treat a longer permitted L as a success-rate guarantee. No imported SR surface was queried in this sweep.

## Reproduce

```sh
.venv/bin/python scripts/run_dynamicvla_smallarrays.py --calibration results/dynamicvla_calibration_20261118/dynamicvla_hbm2_8ch_v1.json --out results/dynamicvla_smallarrays_reproduction
.venv/bin/python scripts/report_dynamicvla_smallarrays.py --root results/dynamicvla_smallarrays_reproduction --out publication/dynamicvla_smallarrays_reproduction
```

Raw arrays remain in the corresponding `results/` directory. Previous pilot/V7/V9 files were not edited.
'''
    (a.out/'REPORT.md').write_text(text)
    hashes = {str(f.relative_to(a.out)): digest(f) for f in a.out.rglob('*')
              if f.is_file() and f.name != 'SHA256.json'}
    (a.out/'SHA256.json').write_text(json.dumps(hashes, indent=2)+'\n')
    print(a.out/'REPORT.md')


if __name__ == '__main__':
    main()
