"""Finalize evidence checks without rewriting any frozen experiment results."""
import argparse
import csv
import json
import math
from pathlib import Path
import shutil

import yaml

from case_v3_main import digest, write_json, write_csv


def read_csv(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--native', type=Path, required=True)
    ap.add_argument('--traces', type=Path, required=True)
    ap.add_argument('--spec', type=Path, required=True)
    ap.add_argument('--snapshot', type=Path, required=True)
    args = ap.parse_args()
    root = args.root
    report = json.loads((args.native / 'isolation_report.json').read_text())
    manifest = json.loads((args.native / 'experiment_manifest.json').read_text())
    if digest(args.native / 'experiment_manifest.json') != report['manifest_sha256']:
        raise ValueError('native manifest identity')
    for name, expected in manifest['source_hashes'].items():
        if digest(args.native / 'executed_sources' / name) != expected:
            raise ValueError('native executed source mismatch')
    for i, row in enumerate(report['runs']):
        n = row['native']
        stats = yaml.safe_load((args.native / f'run_{i:03d}_stats.yaml').read_text())['memory_system']
        if not (n['accepted'] == n['completed'] == sum(n['stream_transactions'].values()) == stats['total_num_read_requests']):
            raise ValueError('native stream accounting')
        served = sum(c['num_read_reqs_served'] for c in stats['controller'])
        classified = sum(c['read_row_hits'] + c['read_row_misses'] + c['read_row_conflicts'] for c in stats['controller'])
        if served != classified or served != n['completed'] or stats['total_num_write_requests'] != 0:
            raise ValueError('native raw statistics')
        if not math.isclose(sum(n['stream_common_window_GBps'].values()), n['achieved_GBps'], abs_tol=1e-9):
            raise ValueError('native window bandwidth')
        if digest(args.native / f'run_{i:03d}.yaml') != row['yaml_sha256'] or digest(args.traces / (row['trace'] + '.csv')) != row['trace_sha256']:
            raise ValueError('native trace/config identity')
    native_rows = [dict(memory=r['memory'], trace=r['trace'], partition=r['partition'], bg=r['bg'],
                        peak_GBps=r['geometry']['peak_GBps'], achieved_GBps=r['native']['achieved_GBps'],
                        vlm_GBps=r['native']['stream_common_window_GBps']['0'],
                        dit_GBps=r['native']['stream_common_window_GBps']['1'], issue_width=r['issue_width'])
                   for r in report['runs']]
    write_csv(root / 'native_isolation.csv', native_rows)
    status = json.loads((root / 'status.json').read_text())
    audit = json.loads((root / 'audit.json').read_text())
    long_status = json.loads((root / 'convergence_followup/status.json').read_text())
    for name, expected in long_status['artifact_hashes'].items():
        if digest(root / 'convergence_followup' / name) != expected:
            raise ValueError('long convergence hash mismatch')
    deep_status = json.loads((root / 'convergence_selected_deep/status.json').read_text())
    for name, expected in deep_status['artifact_hashes'].items():
        if digest(root / 'convergence_selected_deep' / name) != expected:
            raise ValueError('deep convergence hash mismatch')
    selected = read_csv(root / 'selected.csv')
    long_rows = {r['parent_id']: r for r in read_csv(root / 'convergence_followup/sweep.csv') if float(r['requests']) == 480}
    deep_rows = {r['parent_id']: r for r in read_csv(root / 'convergence_selected_deep/sweep.csv') if float(r['requests']) == 3840}
    stability = []
    for row in selected:
        latest = deep_rows.get(row['config_id'], long_rows[row['config_id']])
        stable = max(abs(float(latest['S_vs_previous_pct'])), abs(float(latest['L_vs_previous_pct']))) <= 1.
        stability.append(dict(task=row['task'], track=row['track'], memory=row['memory'], cores=row['n_cores'],
            config_id=row['config_id'], k=row['dit_stages'], requests=int(float(latest['requests'])),
            S_120_ms=row['S_mean_ms'], L_120_ms=row['L_mean_ms'], S_latest_ms=latest['S_ms'], L_latest_ms=latest['L_ms'],
            S_vs_previous_pct=latest['S_vs_previous_pct'], L_vs_previous_pct=latest['L_vs_previous_pct'], stable_1pct=stable))
    write_csv(root / 'selected_stability.csv', stability)
    grid = [r for r in read_csv(root / 'sweep.csv') if r['requests'] == '120' and r['phase'] == 'grid']
    tolerant = []
    eps = 1e-6
    for task in sorted({r['task'] for r in grid}):
        group = [r for r in grid if r['task'] == task]
        for r in group:
            l, s = float(r['L_mean_ms']), float(r['S_mean_ms'])
            if not any(float(o['L_mean_ms']) <= l + eps and float(o['S_mean_ms']) <= s + eps
                       and (float(o['L_mean_ms']) < l - eps or float(o['S_mean_ms']) < s - eps) for o in group):
                tolerant.append(r)
    write_csv(root / 'frontier_tolerant.csv', tolerant)
    best = [r for r in read_csv(root / 'ablation_3.csv') if r['track'] == 'neusim_unsliced_hybrid']
    rule2 = [r for r in best if r['mode'] == 'pipelined' and r['dit_stages'] in ('2', '3') and r['memory'] != 'B1024']
    checks = dict(
        rule1=dict(status='falsified_as_universal', regressions=status['k_regressions'], ties=status['k_ties'],
            diagnosis='12 regressions all VLM1 allocations, k2 underfilled singletons due 100ms timeout. Round weight halves but per-request bytes do not. 72 wait/launch counterfactuals executed; original grid unmodified.'),
        rule2=dict(status='configuration_dependent_not_universal',
            tested_optima=len(rule2), below_5pct_benefit=sum(float(r['S_vs_serial_pct']) > -5 for r in rule2),
            rows=[{k:r[k] for k in ('memory', 'n_cores', 'dit_stages', 'S_mean_ms', 'L_mean_ms', 'S_vs_serial_pct')} for r in rule2],
            interpretation='Not generally a <5% artifact: low-bandwidth LPDDR and BG-fit scenarios show substantial gains. Unisolated HBM/wide-LPDDR 8-core k2 gains are only about2-3%.'),
        rule3=dict(status='native_isolation_pass_exploratory_dse_transfer_only', memories=report['memories'],
            interpretation='BG succeeds at tested saturation ratios; channel fractions do not pass universally; dynamic demand and strict priority not native validated.'),
        rule4=dict(status='falsified_at_1024_under_current_neusim_shapes',
            rows=[{k:r[k] for k in ('n_cores', 'dit_stages', 'S_mean_ms', 'L_mean_ms', 'vlm_cores', 'mode')} for r in best if r['memory'] == 'B1024'],
            interpretation='Optimized k2 equals k3 throughput, but k1 is slower; do not claim k1 already reaches lower bound. Specification narrative and table also conflict.'),
        convergence=dict(short_long=status['max_abs_S_convergence_pct'], followup=long_status,
                         deep_selected=deep_status, selected_remaining_fail_1pct=sum(not r['stable_1pct'] for r in stability)),
        main_conclusion='Mechanism is supported in some explicit fluid/compute scenarios; universal claims and fully native calibrated architecture conclusions remain withheld.')
    write_json(root / 'rule_checks.json', checks)
    final = dict(status='feasible_campaign_complete_with_explicit_scientific_limitations',
        main_grid_executed=True, five_ablations_executed=True, frontier_executed=True,
        simulator_runs=status['rows'], main_neusim_hybrid_runs=status['rows'] // 3,
        analytical_sensitivity_runs=status['rows'] * 2 // 3, native_case_v3_runs=158,
        native_additional_verified=len(report['runs']), diagnostic_counterfactuals=audit['diagnostic_counterfactual_runs'],
        long_convergence_runs=long_status['executed'], raw_rounds_audited=audit['rounds_checked'],
        selected_deep_convergence_runs=deep_status['executed'],
        fully_native_validated=False, unsupported=status['unsupported'],
        k_regressions=status['k_regressions'], k_ties=status['k_ties'],
        long_convergence_fail_1pct=long_status['fail_1pct'],
        selected_remaining_fail_1pct=sum(not r['stable_1pct'] for r in stability),
        neuSim_selected_remaining_fail_1pct=sum(not r['stable_1pct'] for r in stability if r['track'] == 'neusim_unsliced_hybrid'),
        frontier_tolerance_ms=eps, tolerant_frontier_rows=len(tolerant),
        source_manifest_sha256=digest(root / 'experiment_manifest.json'),
        spec_sha256=digest(args.spec), compute_snapshot_sha256=digest(args.snapshot / 'source_manifest.json'),
        native_report_sha256=digest(args.native / 'isolation_report.json'),
        finalize_source_sha256=digest(Path(__file__)),
        provenance_note='Original status.json, CSVs, manifests and raw runs remain immutable. This final status adds follow-up outcomes without changing their hashes.')
    shutil.copy2(Path(__file__), root / 'case_v3_finalize.executed.py')
    shutil.copy2(Path(__file__).with_name('case_v3_report.py'), root / 'case_v3_report.executed.py')
    write_json(root / 'completion_status.json', final)
    print(json.dumps(final, indent=2))


if __name__ == '__main__':
    main()
