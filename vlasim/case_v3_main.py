"""Exhaustive, provenance-pinned Case v3 scenario grid and deterministic ablations.

Native sequential/mixed calibration is not a validation of the fluid sharing model,
priority controller, estimated shapes or analytical row slicing.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import time

from compute_diagnostics import summarize
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


POLICIES = ('fair', 'vlm_priority', 'balance')
TRACKS = ('neusim_unsliced_hybrid', 'analytical_unsliced', 'analytical_sliced')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    if not rows:
        Path(path).write_text('')
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_task(task):
    out = Path(task['out'])
    name = task['id']
    wl = Pi05Workload()
    provider = NeuSimTiming(task['snapshot'], wl, allow_analytical_siglip=True) if task['track'] == TRACKS[0] else None
    calibration = task['calibration']
    dram = DRAMModel(**calibration['params'], version=calibration['version'])
    hw = HWConfig(n_cores=task['cores'], sram_mb=64, local_kb=2048,
                  dram_bw=task['peak_GBps'] * 1e9, slice_mode=task['track'] == TRACKS[2])
    mappings = [MapConfig(mode='serial', vlm_cores=hw.n_cores, dit_stages=1)]
    for split, k, policy, partition in itertools.product(range(1, hw.n_cores), (1, 2, 3), POLICIES, task['partitions']):
        mappings.append(MapConfig(vlm_cores=split, dit_stages=k, bw_policy=policy, stream_partition=partition))
    rows, violations = [], []
    started = time.monotonic()
    with gzip.open(out / (name + '.jsonl.gz'), 'wt') as raw:
        def evaluate(mp, requests, phase):
            result = Simulator(hw, mp, wl=wl, dram=dram, compute_time_fn=provider).run(
                n_requests=requests, warmup=requests // 5, diagnostics=True)
            for r in result['dit_rounds']:
                for rhs in (r['compute_s'] + r['exposed_memory_s'], r['linear_s'] + r['attention_s']):
                    if abs(r['duration_s'] - rhs) > 1e-8:
                        raise ValueError('round timing accounting failure')
            diag = summarize(result)
            config = dict(hardware=asdict(hw), mapping=asdict(mp), requests=requests, warmup=requests // 5,
                          memory=task['memory'], track=task['track'], calibration=calibration['version'])
            cid = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            row = dict(config_id=cid, task=name, phase=phase, track=task['track'], memory=task['memory'],
                       actual_peak_GBps=task['peak_GBps'], **asdict(hw), **asdict(mp), requests=requests,
                       isolation_model='bg_saturated_fit_not_channel_caps' if task['memory'].endswith('-BG') else 'none',
                       warmup=requests // 5, calibration_version=calibration['version'],
                       calibration_sha256=task['calibration_sha256'], frontend_version=task['frontend'],
                       policy_status='fluid_fair_not_native_validated' if mp.bw_policy == 'fair' else 'hypothetical_not_native_validated',
                       scientific_status='synthetic_transition_probe' if task['memory'] == 'B1024' else 'exploratory_native_fitted_fluid',
                       compute_status='estimated_shapes_explicit_siglip_fallback' if provider else 'analytical_sensitivity_not_neusim',
                       busy_scope=diag['busy_scope'], time_accounting=diag['time_accounting'])
            for metric in ('L', 'S'):
                for stat in ('mean', 'std', 'p50', 'p95', 'max'):
                    row[f'{metric}_{stat}_ms'] = float(result[f'{metric}_{stat}']) * 1000
            for field in ('dit_GB_per_req', 'dram_GB_per_req', 'vlm_busy', 'dit_busy', 'kv_on_chip', 'act_on_chip', 'sram_ok'):
                row[field] = result[field]
            row.update(dit_steady_busy=diag['dit_steady_busy'], steady_round_count=diag['steady_round_count'],
                       steady_round_GB=diag['steady_round_mean_GB'], steady_weight_GB=diag['steady_round_mean_weight_GB'])
            row.update({f'round_{k}_ms': v for k, v in diag['steady_round_mean_ms'].items()})
            raw.write(json.dumps(dict(config_id=cid, config=config, result=result), allow_nan=False) + '\n')
            rows.append(row)
            return row

        for mp in mappings:
            for requests in (30, 120):
                evaluate(mp, requests, 'grid')
        primary = [r for r in rows if r['requests'] == 120 and r['mode'] == 'pipelined']
        # Selection rule is declared in the pre-run manifest: best batched k>=2 S,
        # then L, then canonical config identity. Freeze that allocation for all ablations.
        selected = min((r for r in primary if r['dit_stages'] >= 2),
                       key=lambda r: (r['S_mean_ms'], r['L_mean_ms'], r['config_id']))
        selected_mp = MapConfig(**{k: selected[k] for k in asdict(MapConfig())})
        for k in (2, 3):
            mp = MapConfig(**dict(asdict(selected_mp), dit_stages=k, dit_batching=False))
            evaluate(mp, 120, 'unbatched_ablation')
        for split, policy, partition in itertools.product(range(1, hw.n_cores), POLICIES, task['partitions']):
            control = [next(r for r in primary if r['vlm_cores'] == split and r['bw_policy'] == policy
                            and r['stream_partition'] == partition and r['dit_stages'] == k) for k in (1, 2, 3)]
            for r in control[1:]:
                delta = r['S_mean_ms'] - control[0]['S_mean_ms']
                if delta >= -1e-6:
                    violations.append(dict(config_id=r['config_id'], k=r['dit_stages'], split=split, policy=policy,
                        partition=partition, delta_ms=delta, classification='tie_saturation' if abs(delta) <= 1e-6 else 'regression',
                        weight_ratio=r['steady_weight_GB'] / control[0]['steady_weight_GB'],
                        compute_ratio=r['round_compute_ms'] / control[0]['round_compute_ms']))
    write_csv(out / (name + '.csv'), rows)
    summary = dict(id=name, selected_config_id=selected['config_id'], rows=len(rows),
                   wall_seconds=time.monotonic() - started, non_improvements=violations,
                   source_manifest_sha256=task['manifest_sha256'])
    write_json(out / (name + '_summary.json'), summary)
    return summary


def pareto(rows):
    return [r for r in rows if not any(
        other['L_mean_ms'] <= r['L_mean_ms'] and other['S_mean_ms'] <= r['S_mean_ms']
        and (other['L_mean_ms'] < r['L_mean_ms'] or other['S_mean_ms'] < r['S_mean_ms'])
        for other in rows)]


def package(out, tasks, summaries):
    rows = []
    for task in tasks:
        with (out / (task['id'] + '.csv')).open() as stream:
            rows.extend(csv.DictReader(stream))
    numeric = ('L_mean_ms', 'S_mean_ms', 'dit_GB_per_req', 'round_compute_ms', 'round_exposed_memory_ms',
               'steady_weight_GB', 'round_duration_ms', 'dit_busy', 'vlm_busy')
    for row in rows:
        for field in numeric:
            row[field] = float(row[field])
    write_csv(out / 'sweep.csv', rows)
    frontier, selected_rows, convergence = [], [], []
    sections = [[] for _ in range(5)]
    by_summary = {s['id']: s for s in summaries}
    for task in tasks:
        group = [r for r in rows if r['task'] == task['id'] and r['requests'] == '120' and r['phase'] == 'grid']
        frontier.extend(pareto(group))
        selected = next(r for r in group if r['config_id'] == by_summary[task['id']]['selected_config_id'])
        selected_rows.append(selected)
        fixed = [r for r in group if all(r[k] == selected[k] for k in ('mode', 'vlm_cores', 'bw_policy', 'stream_partition'))]
        for r in fixed:
            sections[0].append(r)
        sections[1].extend(r for r in rows if r['task'] == task['id'] and r['phase'] == 'unbatched_ablation')
        sections[1].extend(r for r in fixed if r['dit_stages'] in ('2', '3'))
        serial = next(r for r in group if r['mode'] == 'serial')
        for k in (1, 2, 3):
            best = min((r for r in group if r['mode'] == 'pipelined' and r['dit_stages'] == str(k)), key=lambda r: (r['S_mean_ms'], r['L_mean_ms']))
            sections[2].append(dict(best, S_vs_serial_pct=(best['S_mean_ms'] / serial['S_mean_ms'] - 1) * 100,
                                    L_vs_serial_pct=(best['L_mean_ms'] / serial['L_mean_ms'] - 1) * 100))
        sections[2].append(dict(serial, S_vs_serial_pct=0.0, L_vs_serial_pct=0.0))
        if len(task['partitions']) > 1:
            sections[3].extend(r for r in group if all(r[k] == selected[k] for k in ('mode', 'vlm_cores', 'bw_policy', 'dit_stages')))
        sections[4].extend(r for r in group if all(r[k] == selected[k] for k in ('mode', 'vlm_cores', 'stream_partition', 'dit_stages')))
        short = [r for r in rows if r['task'] == task['id'] and r['requests'] == '30']
        for r in group:
            match = next(s for s in short if all(s[k] == r[k] for k in ('mode', 'vlm_cores', 'dit_stages', 'bw_policy', 'stream_partition')))
            convergence.append(dict(task=task['id'], config_id_120=r['config_id'], config_id_30=match['config_id'],
                                    S_delta_pct=(match['S_mean_ms'] / r['S_mean_ms'] - 1) * 100,
                                    L_delta_pct=(match['L_mean_ms'] / r['L_mean_ms'] - 1) * 100))
    write_csv(out / 'frontier.csv', frontier)
    write_csv(out / 'selected.csv', selected_rows)
    write_csv(out / 'convergence.csv', convergence)
    titles = ('Same Allocation k', 'Batching', 'Fair Serial Comparison', 'Stream Isolation', 'Policy')
    for task in tasks:
        if not task['memory'].endswith('-BG'):
            continue
        bg_group = [r for r in rows if r['task'] == task['id'] and r['requests'] == '120' and r['phase'] == 'grid']
        base_id = task['id'].replace('-BG_', '_')
        base_selected = next(r for r in selected_rows if r['task'] == base_id)
        bg_match = next(r for r in bg_group if all(r[k] == base_selected[k] for k in ('mode', 'vlm_cores', 'dit_stages', 'bw_policy', 'stream_partition')))
        sections[3].extend([base_selected, bg_match])
    lines = ['# Case v3 Ablations', '', 'All times in ms. Tracks and actual memory bandwidth are kept separate. Priority/balance are fluid scenarios, not measured controllers. Analytical slicing is not NeuSim. Selected allocation minimizes batched k>=2 S (tie: L, config hash).', '']
    for i, (title, section) in enumerate(zip(titles, sections), 1):
        write_csv(out / f'ablation_{i}.csv', section)
        lines.extend([f'## {i}. {title}', ''])
        if i == 4:
            lines.extend(['No fixed channel fraction passed all three mix ratios. The paired rows below compare none with the BG saturated-fit scenario at exactly the base-selected mapping. BG shares channels: it is NOT a fixed-p cap model and its fluid generalization is unvalidated.', ''])
        lines.extend(['| Task | Mode | VLM cores | k | Batch | Policy | p | S | L | DiT GB/req | Compute | Exposed | Weight GB/round |',
                      '|---|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|'])
        for r in section:
            lines.append(f"| {r['task']} | {r['mode']} | {r['vlm_cores']} | {r['dit_stages']} | {r['dit_batching']} | {r['bw_policy']} | {r['stream_partition'] or 'none'} | {r['S_mean_ms']:.4f} | {r['L_mean_ms']:.4f} | {r['dit_GB_per_req']:.5f} | {r['round_compute_ms']:.4f} | {r['round_exposed_memory_ms']:.4f} | {r['steady_weight_GB']:.5f} |")
        lines.append('')
    (out / 'ablations.md').write_text('\n'.join(lines) + '\n')
    regressions = [v for s in summaries for v in s['non_improvements'] if v['classification'] == 'regression']
    status = dict(status='exploratory_grid_executed_not_fully_native_validated', rows=len(rows), tasks=len(tasks),
                  frontier_rows=len(frontier), convergence_pairs=len(convergence),
                  max_abs_S_convergence_pct=max(abs(r['S_delta_pct']) for r in convergence),
                  max_abs_L_convergence_pct=max(abs(r['L_delta_pct']) for r in convergence),
                  k_regressions=len(regressions), k_ties=sum(v['classification'] == 'tie_saturation' for s in summaries for v in s['non_improvements']),
                  conclusion_gate='pause_universal_batching_claims_pending_regression_analysis' if regressions else 'accounting_checked_scenario_results_only',
                  unsupported=['real NeuSim row slicing: no verified lowering', 'native strict priority and balance controllers',
                               'exact 256/512 GB/s LPDDR5X presets', 'native end-to-end VLA or task success validation'],
                  slices=dict(neusim_off='executed', neusim_on='unsupported_recorded_in_coverage',
                              analytical_off_on='executed_separate_sensitivity_tracks'),
                  artifact_hashes={p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'status.json'})
    write_json(out / 'status.json', status)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--calib-dir', type=Path, required=True)
    ap.add_argument('--isolation', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    isolation = json.loads(args.isolation.read_text())
    tasks, calibrations = [], {}
    for memory, width in (('M-H256', 8), ('M-L256', 8), ('M-L512', 16)):
        path = args.calib_dir / f'dram_v3_{memory}_mop4_width{width}.json'
        calibration = json.loads(path.read_text())
        measured = isolation['memories'][memory]
        for key in ('eta_seq', 'eta_mix'):
            if abs(calibration['params'][key] - measured[key]) > 1e-12:
                raise ValueError('new calibration does not reproduce frozen reference')
        calibrations[memory] = (calibration, digest(path), measured['peak_GBps'], [None] + measured['supported_channel_partitions'])
        shutil.copy2(path, args.out / path.name)
        if measured['bg_all_ratios_pass']:
            bg_runs = [r for r in isolation['runs'] if r['memory'] == memory and r['bg']]
            balanced = next(r for r in bg_runs if r['trace'] == 'mix_50')
            bg = dict(calibration)
            bg['version'] = calibration['version'] + '_bg_saturated_fit'
            bg['params'] = dict(calibration['params'], eta_mix=balanced['native']['achieved_GBps'] / measured['eta_seq'] / measured['peak_GBps'])
            bg['usable_for_full_case_v3'] = False
            bg['interpretation'] = 'BG shared-channel saturated all-read fit only. Single-stream efficiency transferred from full mapping; VLA dynamic-demand generalization is not native-validated. Not a channel-fraction model.'
            path = args.out / f'dram_v3_{memory}_bg_saturated_fit.json'
            write_json(path, bg)
            calibrations[memory + '-BG'] = (bg, digest(path), measured['peak_GBps'], [None])
    synthetic = dict(version='synthetic_1024_eta85_mix1_not_native', params=dict(eta_seq=.85, eta_mix=1., prio_leak=0.),
                     scope='Hypothetical bandwidth-transition probe, not LPDDR calibration')
    write_json(args.out / 'synthetic_1024.json', synthetic)
    calibrations['B1024'] = (synthetic, digest(args.out / 'synthetic_1024.json'), 1024., [None])
    for (memory, (calibration, sha, peak, partitions)), cores, track in itertools.product(calibrations.items(), (8, 16), TRACKS):
        tasks.append(dict(id=f'{memory}_{cores}c_{track}', memory=memory, cores=cores, track=track,
                          snapshot=str(args.snapshot.resolve()), out=str(args.out.resolve()), calibration=calibration,
                          calibration_sha256=sha, peak_GBps=peak, partitions=partitions,
                          frontend='synthetic' if memory == 'B1024' else 'per-channel-fifo-rr-v1'))
    sources = [Path(__file__), Path(__file__).with_name('compute_diagnostics.py')]
    sources += list((Path(__file__).parent / 'vlasim').glob('*.py'))
    frozen = args.out / 'executed_sources'
    frozen.mkdir()
    for source in sources:
        relative = source.relative_to(Path(__file__).parent)
        target = frozen / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = dict(tasks=tasks, source_hashes={str(p.relative_to(Path(__file__).parent)): digest(p) for p in sources},
                    compute_snapshot_sha256=digest(args.snapshot / 'source_manifest.json'),
                    isolation_sha256=digest(args.isolation), grid='8/16 cores; 64MB shared; 2MB private; bf16;128x128;1GHz; all splits; k1/2/3; 3 policies;120/24 and30/6',
                    selection='min batched k>=2 steady S, then L, then config hash; freeze allocation/policy/partition for ablations',
                    scope='Exploratory fluid DRAM scenarios fitted to native MOP references; analytical sliced/off sensitivity separate from unsliced NeuSim hybrid.')
    write_json(args.out / 'experiment_manifest.json', manifest)
    write_json(args.out / 'coverage.json', dict(executed_tracks=TRACKS, unsupported_track='neusim_sliced',
               reason='Pinned official ChipConfig has square sa_dim and no verified row slicing lowering; do not silently substitute analytical times',
               unsupported_hardware=[dict(memory=m, cores=c, slice_mode=True) for m, c in itertools.product(calibrations, (8, 16))]))
    sha = digest(args.out / 'experiment_manifest.json')
    for task in tasks:
        task['manifest_sha256'] = sha
    summaries = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_task, task) for task in tasks]
        for future in as_completed(futures):
            summary = future.result()
            summaries.append(summary)
            print(json.dumps(summary), flush=True)
    print(json.dumps(package(args.out, tasks, summaries), indent=2), flush=True)


if __name__ == '__main__':
    main()
