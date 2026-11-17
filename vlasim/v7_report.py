"""Publish a bounded V7 paper-data report and independently verifiable manifest."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import platform
import xml.etree.ElementTree as ET

import numpy as np

from v7_common import ROOT, read_csv, write_csv, write_json, load, digest, preservation, truth


def table(rows, keys):
    return ['| ' + ' | '.join(keys) + ' |', '| ' + ' | '.join('---' for _ in keys) + ' |',
            *['| ' + ' | '.join(str(r.get(k, '')) for k in keys) + ' |' for r in rows]]


def attach_stress_and_ratios():
    comparisons = read_csv(ROOT / 'paper/pareto_comparison.csv')
    bw = read_csv(ROOT / 'paper/bandwidth_savings.csv')
    cores = read_csv(ROOT / 'paper/core_savings.csv')
    stress = read_csv(ROOT / 'paper/strict_pair_stress.csv')
    for row in comparisons:
        box = row['Lmax_ms'], row['Smax_ms']
        matched = [r for r in stress if (r['Lmax_ms'], r['Smax_ms']) == box]
        row['bandwidth_savings'] = json.dumps([{k: (v if v != '' else None) for k, v in r.items()}
            for r in bw if (r['Lmax_ms'], r['Smax_ms']) == box], separators=(',', ':'))
        row['core_savings'] = json.dumps([{k: (v if v != '' else None) for k, v in r.items()}
            for r in cores if (r['Lmax_ms'], r['Smax_ms']) == box], separators=(',', ':'))
        for key, idkey, fraction in (('P_lat', 'lat_point_id', 'lat_feasible_fraction'),
                                     ('P_task', 'task_point_id', 'task_feasible_fraction')):
            values = json.loads(row[key])
            lookup = {p[idkey]: p for p in matched}
            for point in values:
                point['empirical_stress_feasible_fraction'] = (float(lookup[point['point_id']][fraction])
                    if point['point_id'] in lookup else None)
                point['stress_scope'] = 'fixed-period empirical quantile scenarios, not probability/CI'
            row[key] = json.dumps(values, separators=(',', ':'))
        row['strict_pair_memberships'] = len(matched)
        row['strict_task_identities'] = len({r['task_point_id'] for r in matched})
        row['strict_task_identities_robust80'] = len({r['task_point_id'] for r in matched
                                                    if float(r['task_feasible_fraction']) >= .8})
    write_csv(ROOT / 'paper/pareto_comparison.csv', comparisons)


def audits():
    prior = preservation(True)
    write_json(ROOT / 'validation/preservation_final.json', prior)
    recheck = load(ROOT / 'validation/recheck_summary.json')
    if not recheck['traffic_accounting_passed']:
        raise RuntimeError('HARD_STOP_traffic_accounting')
    results = {r['point_id']: r for r in read_csv(ROOT / 'validation/recheck_results.csv')}
    required = {r['point_id'] for r in read_csv(ROOT / 'paper/pareto_frontier_points.csv')}
    required.update(r['point_id'] for r in read_csv(ROOT / 'paper/F3_all_feasible_points.csv'))
    required.update(r['point_id'] for r in read_csv(ROOT / 'paper/global_area_selected_points.csv'))
    missing = sorted(required - set(results))
    failed = [p for p in required & set(results) if not truth(results[p]['recheck_passed'])]
    if missing or failed:
        write_json(ROOT / 'validation/publication_coverage_failure.json', dict(missing=missing, failed=failed))
        raise RuntimeError('Final selected-point coverage incomplete')
    coefficients = load(ROOT / 'cost/coefficients.json')
    base = load(ROOT / 'inputs/cost/coefficients.json')
    patch = {'A_phy_LPDDR5', 'A_phy_GDDR6', 'e_dram_LPDDR5', 'e_dram_GDDR6'}
    if any(coefficients['coefficients'][k] != v for k, v in base['coefficients'].items() if k not in patch):
        raise RuntimeError('Unrequested cost coefficient modification')
    with np.load(ROOT / 'cost/draws.npz') as data, np.load(ROOT / 'inputs/cost/draws.npz') as old:
        keys = list(data['keys'])
        if not np.array_equal(data['samples'][:, :old['samples'].shape[1]], old['samples']):
            raise RuntimeError('Frozen MC draws modified')
        expected = data['samples'][:, keys.index('A_phy_HBM2')] / 32 * 28 * data['GDDR6_to_HBM2_PHY_ratio']
        if not np.array_equal(expected, data['samples'][:, keys.index('A_phy_GDDR6')]):
            raise RuntimeError('Correlated PHY draws inconsistent')
    for path in (ROOT / 'paper/figdata').glob('*.csv'):
        if not path.read_text().startswith('# source='):
            raise RuntimeError('Missing figdata source/scope comment')
    task = load(ROOT / 'task/status.json')
    if task['points'] > 16 or task['task_episodes_run'] != 0:
        raise RuntimeError('Task budget/episode accounting failure')
    stages = []
    for path in sorted((ROOT / 'validation').glob('*.xml')):
        suites = list(ET.parse(path).getroot().iter('testsuite'))
        row = dict(path=str(path), tests=sum(int(r.get('tests', 0)) for r in suites),
                   failures=sum(int(r.get('errors', 0)) + int(r.get('failures', 0)) for r in suites))
        if row['failures']:
            raise RuntimeError('Failed pytest evidence')
        stages.append(row)
    for path in (ROOT / 'validation').glob('rechecks/*/status.json'):
        status = load(path)
        for name, sha in status['hashes'].items():
            if digest(path.parent / name) != sha:
                raise RuntimeError('Recheck shard evidence changed')
    for path in (ROOT / 'validation').glob('stress/*/status.json'):
        status = load(path)
        for name, sha in status['hashes'].items():
            if digest(path.parent / name) != sha:
                raise RuntimeError('Stress shard evidence changed')
    raw_count = rounds_count = 0
    maximum_round_error = maximum_traffic_error = 0.
    for path in (ROOT / 'validation').glob('rechecks/*/*.npz'):
        with np.load(path) as data:
            timestamps = data['requests']
            if timestamps.shape != (960, 4) or not np.isfinite(timestamps).all():
                raise RuntimeError('HARD_STOP_raw960_shape_or_nonfinite')
            if np.any(timestamps[:, 3] < timestamps[:, 0]):
                raise RuntimeError('HARD_STOP_raw_negative_latency')
            if 'rounds' in data:
                rounds = data['rounds']
                error = max(float(np.max(np.abs(rounds[:, 2] - rounds[:, 3] - rounds[:, 4]), initial=0)),
                            float(np.max(np.abs(rounds[:, 2] - rounds[:, 5] - rounds[:, 6]), initial=0)))
                maximum_round_error = max(maximum_round_error, error)
                record = load(path.with_suffix('.json'))
                traffic = float(rounds[:, 7].sum()/960/1e9)
                traffic_error = abs(traffic - record['metrics']['dit_GB_per_req'])
                maximum_traffic_error = max(maximum_traffic_error, traffic_error)
                if error > 1e-8 or traffic_error > 1e-8:
                    raise RuntimeError('HARD_STOP_reopened_raw_round_time_or_traffic')
                rounds_count += len(rounds)
        raw_count += 1
    write_json(ROOT / 'validation/reopened_raw_audit.json', dict(passed=True,
        archives=raw_count, round_rows=rounds_count, max_round_time_error_s=maximum_round_error,
        max_DiT_traffic_error_GB_per_req=maximum_traffic_error,
        scope='Independent reopened960 requests and all raw fast-round time/byte reconciliation; no model refit.'))
    plan = {r['point_id']: r for r in read_csv(ROOT / 'validation/stress_plan.csv')}
    reconstructed = {}
    stress_max_error = 0.
    for row in read_csv(ROOT / 'validation/stress_runs.csv'):
        if row['raw'] not in reconstructed:
            point = plan[row['point_id']]
            k = int(point['dit_stages']) if point['mode'] != 'serial' else 1
            with np.load(row['raw']) as data:
                a = data['requests']
                if a.shape != (960, 4) or not np.isfinite(a).all():
                    raise RuntimeError('HARD_STOP_stress_raw960_shape_or_nonfinite')
                stop = 960-k-2
                reconstructed[row['raw']] = (float(np.mean(a[192:stop, 3] - a[192:stop, 0])),
                    float(np.mean(a[192:stop, 3] - a[191:stop-1, 3])))
        L, S = reconstructed[row['raw']]
        error = max(abs(L-float(row['L_s'])), abs(S-float(row['S_s'])))
        stress_max_error = max(stress_max_error, error)
        if error > 1e-8:
            raise RuntimeError('HARD_STOP_reconstructed_stress_LS')
    write_json(ROOT / 'validation/reopened_stress_audit.json', dict(passed=True,
        archives=len(reconstructed), max_LS_absolute_error_s=stress_max_error,
        scope='L/S independently reconstructed from reopened960 raw timestamps, same frozen warmup/tail rule.'))
    write_json(ROOT / 'validation/publication_audit.json', dict(passed=True,
        final_required_points=len(required), all_required960_checked=True, tests=stages,
        unchanged_cost_coefficients_verified=True, correlated_PHY_draws_verified=True,
        prior_deliveries_preserved=True, task_episodes_run=0))
    return stages


def publish():
    attach_stress_and_ratios()
    stages = audits()
    cost = load(ROOT / 'cost/coefficients.json')['coefficients']
    before = load(ROOT / 'paper/pre_recheck/pareto_status.json')
    after = load(ROOT / 'paper/pareto_status.json')
    check = load(ROOT / 'validation/recheck_summary.json')
    stress = load(ROOT / 'validation/stress_summary.json')
    secondary = load(ROOT / 'paper/secondary_status.json')
    task = load(ROOT / 'task/status.json')
    bw = [r for r in read_csv(ROOT / 'paper/bandwidth_savings.csv') if r['BW_task_over_lat']]
    values = np.array([float(r['BW_task_over_lat']) for r in bw])
    patch = [{k: v for k, v in dict(coefficient=name, **cost[name]).items()
              if k in ('coefficient', 'value', 'lower', 'upper', 'source_type', 'status')}
             for name in ('A_phy_LPDDR5', 'A_phy_GDDR6', 'e_dram_LPDDR5', 'e_dram_GDDR6')]
    relations = read_csv(ROOT / 'paper/pareto_comparison.csv')
    main = [r for r in relations if (int(r['Lmax_ms']), int(r['Smax_ms'])) in ((200, 100), (250, 150))]
    front = read_csv(ROOT / 'paper/pareto_frontier_points.csv')
    area = read_csv(ROOT / 'paper/selection_comparison_global_area.csv')
    sensitivity = read_csv(ROOT / 'paper/area_sensitivity.csv')
    thresholds = [r for r in sensitivity if r['phy_break_even_mm2_per_channel']]
    area_improved = sum(float(r.get('area_difference_center_mm2') or 0) < -1e-12 for r in area)
    stress_points = read_csv(ROOT / 'paper/strict_task_point_stress.csv')
    stress_range = (min(float(r['feasible_fraction']) for r in stress_points),
                    max(float(r['feasible_fraction']) for r in stress_points))
    points = read_csv(ROOT / 'task/selected_points.csv')
    low = float(np.min(values)) if len(values) else None
    mid = float(np.median(values)) if len(values) else None
    high = float(np.max(values)) if len(values) else None
    extrema = [dict(statistic=label, value=value, matching_Box_core_rows='; '.join(
        f'({r["Lmax_ms"]},{r["Smax_ms"]}),n={r["n_cores"]}' for r in bw
        if abs(float(r['BW_task_over_lat'])-value) < 1e-12))
        for label, value in (('minimum', low), ('median', mid), ('maximum', high)) if value is not None]
    write_csv(ROOT / 'paper/bandwidth_distribution.csv', extrema)
    robust = stress['strict_task_box_points_robust80']
    total = stress['strict_task_box_points']
    lines = ['# CASE V7 Report', '',
        '## 1. Status', '',
        'V7 resource-Pareto data, secondary literature-cost sensitivities, selected-point timing checks and a16-point real-task measurement request are delivered. '
        'No new DSE grid, no new heldout DRAM experiment, no task episodes and no new cross-host validation were executed.', '',
        *table([
            dict(section='1 Cost patch', status='completed; two Micron centers author-supplied, not independently retrieved'),
            dict(section='2 Resource Pareto', status=f'completed;{after["boxes"]} Boxes, pre/post snapshots retained'),
            dict(section='3 Secondary results', status='completed; correlated2000-draw area sensitivity; same-type energy ratios'),
            dict(section='4 F1-F6', status='completed; CSV source/scope comments plus one rough preview'),
            dict(section='5 Rechecks/stress', status=f'{check["passed"]}/{check["points"]} timing identities passed;'
                 f'{stress["stable_scenarios"]}/{stress["scenario_rows"]} stress rows stable'),
            dict(section='6 Task request', status=f'{task["points"]} proposed points;0 real task episodes')], ['section', 'status']), '',
        f'960 requests per timing check,192 warmup. {check["unique_fast_runs"]} exact-semantic compiled runs; '
        f'{check["unique_python_reference_runs"]} additional original-Python-scheduler references for frontiers/F2/area choices. '
        f'Maximum relative L/S deviation: {check["max_L_relative_error"]:.6g}/{check["max_S_relative_error"]:.6g}; '
        f'maximum Python/compiled timestamp difference{check["max_python_absolute_error_s"]:.6g}s. '
        'Traffic and compute+exposed-memory/linear+attention time conservation passed. '
        'No >1e-6 cross-host difference was observed because no new cross-host comparison ran; frozen prior controls remain evidence, not a new-host claim.', '',
        *table([dict(stage=Path(r['path']).stem, tests=r['tests'], failures=r['failures']) for r in stages],
               ['stage', 'tests', 'failures']), '',
        '## 2. Coefficient Patch', '', *table(patch, ['coefficient', 'value', 'lower', 'upper', 'source_type', 'status']), '',
        'All are literature_estimate, never calibrated. All other V6 coefficients and2000 old draws are unchanged. '
        'LPDDR PHY source is a12nm LPDDR4X x32 design;2.89mm2 minus0.135mm2 sensor bumps, divided by2=1.3775, rounded1.38 perx16. '
        'Bump-limited, no process shrink; LPDDR4X->LPDDR5 proxy is unvalidated. Rambus equal256GB/s PHY ratio1.5-1.75 is directly verified. '
        'GDDR6 area draws equal HBM2 draw/32*28*ratio, not independent draws. '
        'Spartus TableVII independently verifies5.5pJ/bit only, not Micron7.5/6.0. '
        'Micron4 and7.5 centers are explicitly user-supplied vendor claims whose original documents were not independently retrieved. '
        'The specification upper11.3 is rounded from11.25. Source failures and extracted originals are retained undercost/sources/.', '',
        '**cross_type_energy_comparable=false**. Micron device/module accounting and FGDRAM HBM2 accounting differ; '
        'there is no cross-type absolute-energy ranking. Same-type coefficients cancel in ratios.', '',
        '## 3. Primary Resource Results', '',
        f'Before recheck:{before["classifications"]}. After recheck:{after["classifications"]}. '
        f'Excluded timing identities:{len(check["excluded_point_ids"])}. Nominal L/S were never silently replaced.', '',
        'Pareto equality means equality of(n_cores,peak_BW) vector sets, not identical mappings/periods. '
        'Every tied hardware/mapping/SRAM/period identity is retained in the full point tables. '
        'Two empty frontiers are recorded asidentical (empty), not as evidence of feasibility. '
        'The latency-only PRIMARY definition follows V7 literally:serial L<=Smax, all retained periods. '
        'The SECONDARY global-area baseline follows frozen V6:serial Tmin only. '
        'These definitions are explicitly separate.', '',
        *table(extrema, ['statistic', 'value', 'matching_Box_core_rows']), '',
        f'Bandwidth ratios are computed only at matched core counts where BOTH Pareto fronts have points; '
        'missing counts remain null and do not enter the distribution. Core ratios likewise require a matched bandwidth tier. '
        f'SRAM(total shared+private) changes the3D nondominated identity set in{after["SRAM_changes_boxes"]} Boxes; '
        'it is not part of the main2D dominance definition. Per-pair3D dominance is separately recorded.', '',
        f'Empirical stress:{robust}/{total} Box/task-identity memberships remain feasible in>=80% of scenarios '
        f'({robust/total:.3%}). '
        f'{stress["strict_pairs_robust80"]}/{stress["pairs"]} matched strict pairs have BOTH ends feasible in>=80%. '
        f'Individual task feasible fractions range{stress_range[0]:.3%}-{stress_range[1]:.3%};none reaches80%. '
        'These are deterministic scenario fractions, not success probabilities, confidence intervals or independent validation. '
        'Counts retain SRAM/mapping/period identities;resource-collapsed counts must not be inferred from these totals. '
        'Old residuals transferred to repaired identities remain unvalidated. W1 DiT is unmeasured and unchanged.', '']
    for box in main:
        key = int(box['Lmax_ms']), int(box['Smax_ms'])
        lines += [f'### Box{key}: {box["relation"]}', '',
            'Complete frontier identity table below; every row remains linked to its original V6 point.', '',
            *table([r for r in front if (int(r['Lmax_ms']), int(r['Smax_ms'])) == key],
                ['protocol', 'point_id', 'hardware_id', 'mode', 'vlm_cores', 'k', 'batching', 'L_ms', 'S_ms',
                 'n_cores', 'BW_peak_GBps', 'sram_shared_MB', 'private_KB_per_core', 'conditional_status']), '']
    lines += ['## 4. Secondary Results', '',
        f'{len(sensitivity)} strict point-pair/Box memberships analyzed;{len(thresholds)} have finite same-type PHY thresholds. '
        'Repeated hardware pairs are explicit identity memberships, not independent experiments. '
        'Cross-type areas are computed butmarkedcross_type; no single-PHY break-even is invented for them. '
        'For identical channel counts common PHY cancels, so no finite PHY threshold exists. '
        'MC fixed-pair lower-area fractions and globally reoptimized ranking fractions are distinct model sensitivities.', '',
        f'At central literature coefficients,{area_improved}/22 Boxes select a strictly lower-area task-aware design. '
        'In both main example Boxes, the central minimum-area hardware is the same for latency-only and task-aware; '
        'a resource-frontier extension is not evidence of lower total estimated area.', '',
        *table(area, ['Lmax_ms', 'Smax_ms', 'latency_only_hardware_id', 'task_aware_hardware_id',
                      'area_difference_center_mm2', 'MC_fixed_pair_task_lower_fraction',
                      'MC_reoptimized_task_lower_fraction', 'cross_type']), '',
        f'Same-type traffic/MAC comparisons:{secondary["energy_ratios"]}; DRAM energy-ratio cancellation checks all passed. '
        'F2 uses a common hardware and common allocation across all five k/batching controls. '
        'Full-run drain traffic and steady traffic are separately named; primary traffic uses steady bandwidth*period.', '',
        '## 5. Figure Data', '',
        *table([dict(figure=key, path=str(p.relative_to(ROOT)), rows=len(read_csv(p)))
                for key in ('F1', 'F2', 'F3', 'F4', 'F5', 'F6')
                for p in sorted((ROOT / 'paper/figdata').glob(key + '_*.csv'))], ['figure', 'path', 'rows']), '',
        'Every CSV starts with a comment recording source path, primary/secondary scope and conditional status. '
        'F3 includes every feasible curve identity and separate dominance arrows. '
        'Preview:results/v7/paper/preview.png; rough only. Automated nonblank check passed; '
        'image viewing was unavailable, so human/visual QA is not claimed. No final styled figures were produced.', '',
        '## 6. Real-Task Measurement Request', '',
        *table(points, ['point_id', 'hardware_id', 'mode', 'k', 'batching', 'L_960_ms', 'S_960_ms',
                        'priority', 'supported_claim']), '',
        'Full protocol:task/measurement_request_v7.md. Four low-L references and two outside-platform counterexamples included. '
        'There are no main-Box strict pairs, so none are fabricated; main-Box alternatives are labeled as tradeoffs/equality. '
        'Environment/checkpoint/trial/latency/chunk inputs remain null. Both invalid-as-failure and invalid-excluded protocols are mandatory; '
        'all-invalid excluded rate is null. Zero episodes executed.', '',
        '## 7. Limitations', '',
        '- GDDR6_c16/c24 use conditional NoRefresh and median seq eligibility;small grains do not all pass0.8. '
        'This is not physically refreshed GDDR6 validation.',
        '- No new heldout data, no fitting on heldout, no task evaluation and no new cross-host run. '
        'Compiled960 checks for nonfrontier F3 points are consistency checks within the frozen model, not independent timing validation.',
        '- All area estimates retain V6 synthesis/extrapolation limitations:no achieved timing/P&R/silicon calibration. '
        'Two energy centers are author-supplied vendor claims;LPDDR PHY is a previous-generation proxy.',
        '- Search pruning, discrete SRAM/core choices and five retained period multipliers limit the candidate space; '
        'global means minimum among retained discrete candidates, never continuous or exhaustive architecture optimality.',
        '- Empirical quantile scenarios are not probabilities, confidence intervals or closed-loop task robustness.', '',
        '## 8. Reproduction And Hashes', '',
        'Inputs:results/v7/inputs/manifest.json. Frozen original V7 spec:results/v7/NEXT_STEPS_V7.md. '
        'V6 and earlier deliveries are unchanged; cold evidence remains in verified archives.', '',
        '```sh', 'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_prepare.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_sources.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_cost.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_pareto.py pre_recheck',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_finish.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v7_report.py verify', '```', '',
        'Source acquisition failures are retained, not hidden; all derived coefficients are explicitly attributed. '
        'Execution logs and copied executed sources:results/v7/execution/. Recheck/stress shards each carry hashes and support exact-input resume. '
        'For historical executed code use the matching execution snapshot; do not assume later source edits were the executed revision. '
        'delivery_manifest.json hashes all final artifacts except itself, delivery_verification.json and the self-writing08 publication/verification logs, plus current implementation/tests/report. '
        'Verify before modifying/rerunning. Existing successful checkpoints are reused, never silently recomputed with different inputs.']
    report = Path('docs/CASE_V7_REPORT.md')
    report.write_text('\n'.join(lines)+'\n')
    write_json(ROOT / 'status.json', dict(status='delivered_resource_pareto_with_explicit_source_limitations',
        boxes=22, task_episodes_run=0, new_DSE_grid=False, new_heldout=False,
        new_cross_host_comparison=False, cost_scope='secondary_literature_cost',
        Micron_energy_centers_independently_verified=False, cross_type_energy_comparable=False,
        recheck=check, stress=stress, latest_pytest=stages[-1] if stages else None))
    excluded = {'delivery_manifest.json', 'delivery_verification.json'}
    artifacts = {str(p.relative_to(ROOT)): digest(p) for p in sorted(ROOT.rglob('*'))
                 if p.is_file() and str(p.relative_to(ROOT)) not in excluded
                 and not any(part.startswith('08_') for part in p.relative_to(ROOT).parts)}
    sourcepaths = [*Path('vlasim').glob('v7_*.py'), Path('tests/test_v7.py'), report,
                   Path('vlasim/v6_band.py'), Path('vlasim/v6_periodic.cpp'), Path('vlasim/v51_fast.py'),
                   Path('vlasim/v4_scheduler.py')]
    write_json(ROOT / 'delivery_manifest.json', dict(status='delivered_with_explicit_limits',
        artifacts_sha256=artifacts, sources_sha256={str(p): digest(p) for p in sourcepaths},
        task_episodes_run=0, platform=platform.platform()))
    print('Published V7', len(artifacts), 'artifacts', flush=True)


def verify():
    manifest = load(ROOT / 'delivery_manifest.json')
    changed = [str(ROOT / p) for p, sha in manifest['artifacts_sha256'].items() if digest(ROOT / p) != sha]
    changed += [p for p, sha in manifest['sources_sha256'].items() if digest(p) != sha]
    write_json(ROOT / 'delivery_verification.json', dict(passed=not changed,
        artifacts=len(manifest['artifacts_sha256']), sources=len(manifest['sources_sha256']), mismatches=changed))
    if changed:
        raise RuntimeError('Delivery verification failed')
    print('Verified V7', len(manifest['artifacts_sha256']), 'artifacts', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('publish', 'verify'))
    publish() if parser.parse_args().action == 'publish' else verify()
