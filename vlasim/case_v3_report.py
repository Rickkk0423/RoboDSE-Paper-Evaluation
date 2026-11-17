"""Audit completed Case v3 artifacts, extract requested diagnostics and report gates."""
import argparse
import csv
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from compute_diagnostics import summarize
from vlasim import HWConfig, MapConfig, Simulator, DRAMModel
from vlasim.sim import split_steps
from vlasim.workload import Pi05Workload
from vlasim.neusim_compute import NeuSimTiming


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def csv_rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)


def close(a, b):
    if not np.isclose(a, b, rtol=1e-9, atol=1e-9):
        raise ValueError(f'accounting mismatch: {a} != {b}')


def audit(out):
    manifest = json.loads((out / 'experiment_manifest.json').read_text())
    status = json.loads((out / 'status.json').read_text())
    for name, expected in manifest['source_hashes'].items():
        if sha(out / 'executed_sources' / name) != expected:
            raise ValueError('frozen source hash mismatch: ' + name)
    for name, expected in status['artifact_hashes'].items():
        if sha(out / name) != expected:
            raise ValueError('artifact hash mismatch: ' + name)
    rows = csv_rows(out / 'sweep.csv')
    indexed = {r['config_id']: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError('duplicate grid identities')
    for task in manifest['tasks']:
        expected = 2 * (1 + (task['cores'] - 1) * 3 * 3 * len(task['partitions'])) + 2
        if sum(r['task'] == task['id'] for r in rows) != expected:
            raise ValueError('incomplete grid: ' + task['id'])
    extracted, non_improvements, checked, rounds_checked = [], [], 0, 0
    selected_ids = {r['config_id'] for r in csv_rows(out / 'ablation_1.csv') if r['track'] == 'neusim_unsliced_hybrid'}
    selected_ids.update(r['config_id'] for r in rows if r['track'] == 'neusim_unsliced_hybrid' and r['mode'] == 'serial' and r['requests'] == '120')
    bad_ids = set()
    for path in sorted(out.glob('*_summary.json')):
        summary = json.loads(path.read_text())
        for v in summary['non_improvements']:
            non_improvements.append(dict(task=summary['id'], **v))
            if v['classification'] == 'regression':
                bad_ids.add(v['config_id'])
    selected_ids.update(bad_ids)
    wl = Pi05Workload()
    for path in sorted(out.glob('*.jsonl.gz')):
        with gzip.open(path, 'rt') as stream:
            for line in stream:
                record = json.loads(line)
                cfg, result = record['config'], record['result']
                row = indexed[record['config_id']]
                calculated = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
                if calculated != record['config_id']:
                    raise ValueError('raw config identity mismatch')
                k = cfg['mapping']['dit_stages'] if cfg['mapping']['mode'] == 'pipelined' else 1
                steps = split_steps(wl.c.flow_steps, k)
                for r in result['dit_rounds']:
                    active = [steps[i] for i, req in enumerate(r['stage_request_ids']) if req is not None]
                    weight_rounds = max(active) if cfg['mapping']['dit_batching'] else sum(active)
                    weight = wl.dit_layer_params * wl.c.w_bytes * wl.c.dit_layers * weight_rounds
                    kv = 0 if result['kv_on_chip'] else wl.kv_layer_bytes * wl.c.dit_layers * sum(active)
                    close(r['weight_bytes'], weight)
                    close(r['dram_bytes'], weight + kv)
                    close(r['duration_s'], r['compute_s'] + r['exposed_memory_s'])
                    close(r['duration_s'], r['linear_s'] + r['attention_s'])
                    rounds_checked += 1
                dit = sum(r['dram_bytes'] for r in result['dit_rounds']) / cfg['requests'] / 1e9
                close(dit, result['dit_GB_per_req'])
                vlm_bytes = sum(op.dram_bytes for op in wl.vlm_ops(result['kv_on_chip'], cfg['mapping']['vlm_util'], result['act_on_chip']))
                close(dit + vlm_bytes / 1e9, result['dram_GB_per_req'])
                close(float(row['dit_GB_per_req']), dit)
                trace = np.array(result['trace'])
                for metric, values in (('L', trace[:, 1] - trace[:, 0]), ('S', np.diff(trace[:, 1]))):
                    for stat, value in (('mean', values.mean()), ('std', values.std()), ('p50', np.percentile(values, 50)), ('p95', np.percentile(values, 95)), ('max', values.max())):
                        close(result[f'{metric}_{stat}'], value)
                        close(float(row[f'{metric}_{stat}_ms']), value * 1000)
                if record['config_id'] in selected_ids:
                    diag = summarize(result)
                    extracted.append(dict(row, config=cfg, **diag, dit_rounds=result['dit_rounds'],
                                          extraction_reason='regression' if record['config_id'] in bad_ids else 'selected_same_allocation_or_serial'))
                checked += 1
    if checked != len(rows):
        raise ValueError('raw/CSV count mismatch')
    write_csv(out / 'k_non_improvements.csv', non_improvements)
    write_json(out / 'compute_report.json', dict(
        experiment_manifest_sha256=sha(out / 'experiment_manifest.json'),
        scope='Unsliced real NeuSim estimated-shape hybrid; SigLIP explicit analytical fallback; DRAM fluid scenarios, not native end-to-end simulation. Selected frozen mapping k1/2/3 plus serial and regressions. Busy is occupied wall time, not PE utilization. Round weight ratio is NOT per-request weight ratio when rounds are underfilled.',
        hybrid_results=extracted))
    return dict(configurations=checked, rounds_checked=rounds_checked, source_hashes_verified=len(manifest['source_hashes']),
                k_regressions=len(bad_ids), provenance='frozen executed sources and all pre-existing artifact hashes checked',
                accounting='all rounds reconstructed from active stages, weights/KV reconciled, all L/S stats recomputed from trace')


def regression_probes(out, snapshot):
    records = json.loads((out / 'compute_report.json').read_text())['hybrid_results']
    bad = [r for r in records if r['extraction_reason'] == 'regression']
    if not bad:
        return []
    target = out / 'regression_probes'
    target.mkdir(exist_ok=False)
    frozen = dict(source_sha256=sha(Path(__file__)), input_report_sha256=sha(out / 'compute_report.json'),
                  snapshot_sha256=sha(snapshot / 'source_manifest.json'),
                  source_manifest_sha256=sha(out / 'experiment_manifest.json'),
                  cases=[dict(config_id=r['config_id'], wait=wait, launch=launch)
                         for r in bad for wait in (0., .1, 1.) for launch in ('jit', 'eager')],
                  scope='Diagnostic counterfactuals only; original main grid unchanged; no post-hoc parameter promotion')
    write_json(target / 'experiment_manifest.json', frozen)
    wl = Pi05Workload()
    provider = NeuSimTiming(snapshot, wl, allow_analytical_siglip=True)
    manifest = json.loads((out / 'experiment_manifest.json').read_text())
    tasks = {t['id']: t for t in manifest['tasks']}
    rows = []
    with gzip.open(target / 'runs.jsonl.gz', 'wt') as raw:
        for record in bad:
            cfg = record['config']
            dram = DRAMModel(**tasks[record['task']]['calibration']['params'])
            for wait in (0., .1, 1.):
                for launch in ('jit', 'eager'):
                    mp = MapConfig(**dict(cfg['mapping'], max_wait=wait, vlm_launch=launch))
                    result = Simulator(HWConfig(**cfg['hardware']), mp, wl=wl, dram=dram,
                                       compute_time_fn=provider).run(120, 24, diagnostics=True)
                    diag = summarize(result)
                    row = dict(parent_id=record['config_id'], task=record['task'], policy=mp.bw_policy,
                               k=mp.dit_stages, max_wait=wait, launch=launch, S_ms=result['S_mean'] * 1000,
                               L_ms=result['L_mean'] * 1000, dit_GB_per_req=result['dit_GB_per_req'],
                               steady_active_requests=diag['steady_round_mean_active_requests'],
                               rounds=diag['steady_round_count'], **diag['steady_round_mean_ms'])
                    rows.append(row)
                    raw.write(json.dumps(dict(config=dict(hardware=cfg['hardware'], mapping=asdict(mp)),
                                              parent_id=record['config_id'], result=result)) + '\n')
    write_csv(target / 'sweep.csv', rows)
    return rows


def report(out, audit_result, probes):
    best = csv_rows(out / 'ablation_3.csv')
    selected = csv_rows(out / 'selected.csv')
    status = json.loads((out / 'status.json').read_text())
    lines = ['# Case v3 Full Execution Report', '',
        'This report completes the feasible experiment campaign, not full native validation. The input specification is dated 2026-11-16; the supplied local task date is 2026-11-15. No expected value is treated as a measurement.', '',
        f"Executed {audit_result['configurations']} simulator configurations in {status['tasks']} separately grouped tasks; audited {audit_result['rounds_checked']} rounds. Native MOP calibration/isolation adds 54 runs to the preserved 104 P0/diagnostic runs (158 total for Case v3).", '',
        '## Main Unsliced NeuSim Hybrid Results', '',
        'S and L in ms. Each k is independently optimized over all splits and fluid policies; serial uses all cores. BG means a saturated all-read BG fit, not validated dynamic VLA isolation. M-L256/M-L512 actually peak at 204.8/409.6 GB/s. B1024 is synthetic.', '',
        '| Scenario | Cores | Mode | k | VLM:DiT | Policy | S | L | S vs serial |',
        '|---|---:|---|---:|---|---|---:|---:|---:|']
    for r in best:
        if r['track'] != 'neusim_unsliced_hybrid':
            continue
        cores, split = int(r['n_cores']), int(r['vlm_cores'])
        lines.append(f"| {r['memory']} | {cores} | {r['mode']} | {r['dit_stages']} | {split}:{cores-split} | {r['bw_policy']} | {float(r['S_mean_ms']):.4f} | {float(r['L_mean_ms']):.4f} | {float(r['S_vs_serial_pct']):+.2f}% |")
    lines.extend(['', '## Falsification And Scope', '',
        f"- Universal strict batching improvement fails: {status['k_regressions']} regressions and {status['k_ties']} ties (tolerance 1e-6 ms). Ties are reported separately; no universal batching claim is made.",
        '- Regressions occur with severely VLM-starved allocations. Round weights may halve while requests span multiple underfilled rounds; per-round savings must not be called per-request savings. See compute_report.json and regression_probes/sweep.csv for actual occupancy, bytes, waits and diagnostic counterfactuals.',
        f"- All-grid 30/120 maximum absolute S/L changes: {status['max_abs_S_convergence_pct']:.4f}% / {status['max_abs_L_convergence_pct']:.4f}%. These are reported, not automatically accepted as convergence.",
        '- Native MOP BG isolation passes the three tested ratios on all three memories. No fixed channel fraction passes all ratios; fixed-p DSE promotion is withheld. BG fitting is a separate exploratory scenario and does not demonstrate strict priority.',
        '- The 409.6 GB/s LPDDR calibration uses issue16 to remove the known issue8 injector ceiling. The 64 KiB sequential case remains below 80%; this limitation is not hidden by the median fit.',
        '- Real NeuSim row slicing is unsupported. Separate analytical off/on grids are complete and never mixed into real NeuSim frontiers. Coverage records the unsupported native track instead of pretending it ran.',
        '- Strict priority, balance hardware, estimated checkpoint shapes, vector/norm/NoC costs, real VLA replay, physical silicon and task success remain unvalidated. No area/energy or chip recommendation is made.', '',
        '## Delivered Evidence', '',
        '- sweep.csv: complete feasible grid and fixed-allocation unbatched controls; all timing statistics, bytes, occupancy, SRAM flags and configuration identity.',
        '- frontier.csv: Pareto sets partitioned by core count, actual memory/scenario and compute track; no cross-track mixing.',
        '- ablations.md and ablation_1..5.csv: all five comparisons, including paired BG scenarios and fixed-allocation policy comparisons.',
        '- compute_report.json: selected real NeuSim same-allocation k1/2/3, serial and every regression, with complete per-round timing.',
        '- convergence.csv, k_non_improvements.csv, regression_probes/: exhaustive short/long pairing and investigated counterexamples.',
        '- experiment_manifest.json, executed_sources/, *.jsonl.gz, audit.json: frozen inputs, source SHA-256 and raw per-configuration evidence.', ''])
    (out / 'REPORT.md').write_text('\n'.join(lines))
    audit_result['diagnostic_counterfactual_runs'] = len(probes)
    audit_result['reporter_sha256'] = sha(Path(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--snapshot', type=Path, required=True)
    args = ap.parse_args()
    result = audit(args.out)
    probes = regression_probes(args.out, args.snapshot)
    report(args.out, result, probes)
    result['generated_hashes'] = {p.name: sha(p) for p in args.out.iterdir() if p.is_file() and p.name not in ('audit.json', 'status.json')}
    write_json(args.out / 'audit.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
