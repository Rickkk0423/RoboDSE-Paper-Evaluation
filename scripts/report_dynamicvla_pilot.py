"""Publish compact, explicitly exploratory pilot tables without modifying V7/V9."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics


def load(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def table(headers, values):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] +
                     ['| '+' | '.join(map(str, row))+' |' for row in values])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    profile = load(a.root/'profile_complete/profile.json')
    verified = load(a.root/'verification.json')
    assert verified['passed']
    names = ('dse', 'dse_sram8', 'dse_sram64')
    summaries = {name: load(a.root/name/'summary.json') for name in names}
    data = {name: rows(a.root/name/'candidate_points.csv') for name in names}
    base = [r for r in data['dse'] if float(r['factor']) == 1]
    controlled = [r for r in base if r['memory'] == 'LPDDR5_c4' and r['cores'] == '4'
                  and (r['mode'] == 'serial' or r['vlm_cores'] == '2')]
    serial = [r for r in base if r['mode'] == 'serial']
    controls = []
    for r in controlled:
        label = 'Serial (all 4 cores)' if r['mode'] == 'serial' else (
            f'Pipeline k={r["k"]}, '+('batched' if r['batching'] == 'True' else 'unbatched'))
        controls.append([label, *[f'{float(r[k]):.3f}' for k in
            ('L_ms', 'S_ms', 'steady_dit_GB_per_req', 'steady_dram_GB_per_req')]])
    core_table = []
    for n in (1, 2, 3, 4, 6, 8):
        core_table.append([n]+[f'{float(next(r for r in serial if r["cores"] == str(n) and r["memory"] == m)["S_ms"]):.3f}'
                              for m in ('LPDDR5_c4', 'LPDDR5_c8', 'LPDDR5_c16')])
    sram_rows = []
    for name in ('dse_sram8', 'dse', 'dse_sram64'):
        for k in (1, 2, 3):
            r = next(r for r in data[name] if float(r['factor']) == 1 and r['memory'] == 'LPDDR5_c4'
                     and r['cores'] == '4' and r['mode'] == 'pipelined' and r['vlm_cores'] == '2'
                     and r['k'] == str(k) and r['batching'] == 'True')
            sram_rows.append([r['sram_mb'], k, f'{float(r["L_ms"]):.3f}', f'{float(r["S_ms"]):.3f}'])
    boxes = []
    for l, s in ((40, 40), (80, 40), (120, 40), (80, 80), (120, 80)):
        for arm in ('serial', 'no_batching', 'full'):
            eligible = [r for r in data['dse'] if float(r['L_ms']) <= l and float(r['S_ms']) <= s
                        and (arm == 'full' or r['mode'] == 'serial' or
                             (arm == 'no_batching' and (r['k'] == '1' or r['batching'] == 'False')))]
            vectors = {(float(r['peak_GBps']), int(r['cores'])) for r in eligible}
            frontier = sorted(v for v in vectors if not any(w != v and w[0] <= v[0] and w[1] <= v[1] for w in vectors))
            boxes.append(dict(Lmax_ms=l, Smax_ms=s, arm=arm, resource_frontier=frontier))
    for name in names:
        target = a.out/name
        target.mkdir(exist_ok=True)
        for file in ('summary.json', 'manifest.json', 'candidate_points.csv', 'configurations.csv',
                     'checks960.csv', 'best_refresh.csv'):
            shutil.copy2(a.root/name/file, target/file)
    shutil.copy2(a.root/'profile_complete/profile.json', a.out/'profile.json')
    shutil.copy2(a.root/'verification.json', a.out/'verification.json')
    (a.out/'timing_box_frontiers.json').write_text(json.dumps(boxes, indent=2)+'\n')
    prefix_ms = statistics.mean(t for label, t in profile['phase_ms'] if label == 'prefix')
    dit_ms = statistics.mean(t for label, t in profile['phase_ms'] if label == 'dit')
    baseline = next(r for r in controlled if r['mode'] == 'pipelined' and r['k'] == '1')
    benefits = []
    for k in ('2', '3'):
        r = next(r for r in controlled if r['k'] == k and r['batching'] == 'True')
        benefits.append(dict(k=int(k), S_reduction_pct=100*(1-float(r['S_ms'])/float(baseline['S_ms'])),
                             dit_traffic_reduction_pct=100*(1-float(r['steady_dit_GB_per_req'])/float(baseline['steady_dit_GB_per_req'])),
                             total_traffic_reduction_pct=100*(1-float(r['steady_dram_GB_per_req'])/float(baseline['steady_dram_GB_per_req']))))
    (a.out/'controlled_benefits.json').write_text(json.dumps(benefits, indent=2)+'\n')
    report = f'''# DynamicVLA Small-Core Pilot

Date: 2026-11-18. Status: exploratory hardware-model results, not paper-ready physical or task validation.

## What Actually Ran

- Dedicated Slurm GPU job {profile['slurm_job']} on {profile['host']}, {profile['gpu']}, submitted via einst.
- Loaded the real DOM checkpoint; checkpoint SHA-256: `{profile['checkpoint_sha256']}`.
- {profile['parameter_elements']:,} parameter elements; {profile['parameter_bytes']/1e9:.3f} GB runtime parameter storage, mixed FP32/BF16.
- Synthetic fixed input: two cameras, two observation frames, one short instruction; H=20; 10 denoising steps; prefix length {profile['kv_cache']['prefix_tokens']}.
- Two warmups, five timed requests, then one traced request. Output [1,20,7], finite; repeat/trace max absolute error both zero.
- Instrumented host inference mean {statistics.mean(profile['inference_ms']):.3f} ms; prefix CUDA-event mean {prefix_ms:.3f} ms; DiT mean {dit_ms:.3f} ms per step ({10*dit_ms:.3f} ms for ten steps).
- These are GPU sanity timings for one input, not NPU timing validation, a representative task distribution, or a performance guarantee.
- No shared service modified; no robotic episodes; no real cross-chunk batching implementation executed.

The first GPU job (2069194) failed while saving due to Python 3.10 lacking hashlib.file_digest. Job 2069213 completed but omitted composite attention matmul events. Its trace was rejected for DSE. Job 2069331 includes these events and is the sole DSE input. The earlier dev-queue request 2069160 was cancelled while pending; no unrelated jobs were cancelled.

## Hardware Search

- Main sweep: cores 1/2/3/4/6/8; LPDDR5 51.2/102.4/204.8 GB/s; 32 MB shared SRAM; 512 KB private SRAM per core.
- Each core is a 128x128 array at 1 GHz. Core count is not interchangeable with GPU cores or SMs.
- All nonempty VLM/DiT splits; serial; pipeline k=1; k=2/3 with and without batching. One-core hardware supports only serial in this implementation.
- Supplemental 8 MB and 64 MB SRAM sweeps cover 1/2/3/4 cores at all three bandwidths.
- {sum(v['configurations'] for v in summaries.values())} configurations and {sum(v['candidate_points'] for v in summaries.values())} retained timing points across 42 hardware identities.
- Search uses 480 requests and 96 warmup requests. Each configuration's minimum stable-period point has a 960-request/192-warmup consistency check. Other curve factors are not all rechecked at 960 requests.
- Maximum 480/960 relative timing difference: {max(v['max_check_relative_error'] for v in summaries.values()):.3e}.
- Six 24-request Python/C++ reference comparisons also passed. These are consistency checks, not independent physical calibration.

## Controlled Batching Result

51.2 GB/s, 4 cores, 32 MB SRAM. Every pipeline row fixes allocation at 2 VLM + 2 DiT cores. Serial uses all four cores for each phase. Traffic values are model estimates, not GPU DRAM counters.

{table(['Organization','L (ms)','S (ms)','DiT GB/request','Total GB/request'], controls)}

Relative to the k=1 pipeline control, k=2 reduces S by {benefits[0]['S_reduction_pct']:.2f}%, DiT traffic by {benefits[0]['dit_traffic_reduction_pct']:.2f}%, and total traffic by {benefits[0]['total_traffic_reduction_pct']:.2f}%. At k=3 these reductions are {benefits[1]['S_reduction_pct']:.2f}%, {benefits[1]['dit_traffic_reduction_pct']:.2f}%, and {benefits[1]['total_traffic_reduction_pct']:.2f}%. Longer L is the tradeoff. The 10-step schedule splits unevenly at k=3 (4/3/3), so traffic does not fall to exactly one third.

## Does Fewer Cores Make Sense?

Serial refresh interval, 32 MB SRAM:

{table(['Cores','51.2 GB/s: S (ms)','102.4 GB/s: S (ms)','204.8 GB/s: S (ms)'], core_table)}

In this model, small-core designs merit priority: adding cores alone gives diminishing returns at fixed bandwidth. This does not mean the vision prefix is negligible: traced matrix/conv work is {summaries['dse']['prefix_GFLOP']:.3f} GFLOP for the prefix and {summaries['dse']['dit_GFLOP']:.3f} GFLOP for ten DiT steps. Model parameter count alone is insufficient to size compute.

## SRAM Sensitivity

Same 51.2 GB/s, four cores and 2+2 split:

{table(['Shared SRAM (MB)','k, batching enabled','L (ms)','S (ms)'], sram_rows)}

The trace-derived full-output activation working-set estimate is {summaries['dse']['activation_working_set_MB']:.3f} MB. At 8 MB, modeled prefix spilling increases S: batching still helps, but the 32 MB result cannot be transferred unchanged to a smaller-SRAM chip. This estimate is not a tile-level allocation or compiler liveness analysis.

## Timing Boxes Are Not Success Contours

The supplemental `timing_box_frontiers.json` uses 40 ms-related timing boxes for hardware screening only:

{table(['Box Lmax/Smax (ms)','Search arm','Pareto vectors (GB/s, cores)'], [[str(b['Lmax_ms'])+'/'+str(b['Smax_ms']), b['arm'], str(b['resource_frontier'])] for b in boxes])}

These frontiers compare bandwidth/core vectors only at fixed 32 MB SRAM. They are not area Pareto sets or matched-SR results. At 102.4 GB/s even one-core serial is below 40 ms in the model. The current robotic harness cannot demonstrate arbitrary extra refresh gains below its 40 ms control period. At 51.2 GB/s the serial/batched trajectories cross control-step-relevant ranges, making that bandwidth more informative for eventual validation. Rounded or quantized timings must be reported as a different protocol, not silently substituted for the original hardware point.

## Evidence Limits and Next Step

1. Target arithmetic is uniformly BF16, while the loaded checkpoint uses mixed precision. No numerical equivalence test of that conversion was performed.
2. Traced linear and attention GEMMs use the pinned NeuSim provider. Vision convolutions use an analytical compute estimate; normalization, softmax, elementwise work, biases and other movement are not fully modeled.
3. Memory uses the historical Ramulator-calibrated fluid model. No new Ramulator process was invoked for this pilot, and the fit has not been validated for DynamicVLA traces.
4. Traffic assumes streamed matrix weights, approximate prefix spills and uniform KV read/write placement. Cache reuse and tile-level activation liveness need a dedicated mapping/calibration pass.
5. The synthetic short prompt gives 78 prefix tokens. Longer instructions or other input protocols require new traces. Batching effects are modeled, not measured on the deployed policy.
6. Prioritize 1-4 cores and 8/32 MB SRAM, retain 6/8 cores as controls, calibrate representative DynamicVLA memory/vision workloads, and test mixed-timestep batched DiT output equivalence before claiming hardware or task gains. Defer SR rollouts until those timing assumptions are credible.

## Reproduce

From the project root, using the delivered profile:

```sh
.venv/bin/python scripts/run_dynamicvla_pilot.py --profile publication/dynamicvla_pilot/profile.json --out results/dynamicvla_reproduction
```

Use `--cores 1,2,3,4 --sram-mb 8` or `--sram-mb 64` with distinct output directories for supplemental sweeps. Raw search/recheck arrays and failed-probe logs remain under `results/dynamicvla_pilot_20261118/`; the compact publication directory contains tables, manifests, the successful trace and verification results. Frozen V7/V9 results were not modified.
'''
    (a.out/'REPORT.md').write_text(report)
    manifest = {str(f.relative_to(a.out)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in a.out.rglob('*') if f.is_file() and f.name != 'SHA256.json'}
    (a.out/'SHA256.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(a.out/'REPORT.md')


if __name__ == '__main__':
    main()
