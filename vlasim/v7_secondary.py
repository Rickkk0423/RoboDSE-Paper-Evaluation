"""Secondary area comparisons and same-type traffic ratios, never energy ranking."""
import argparse
from collections import Counter
import numpy as np

from v7_common import (ROOT, BOXES, candidates, read_csv, write_csv, write_json,
                       feasible, load, summary)
from v7_cost import area_data, area_feature
from vlasim.workload import Pi05Workload


def run(phase='pre_recheck'):
    out = ROOT / ('paper/pre_recheck' if phase == 'pre_recheck' else 'paper')
    rows = candidates()
    if phase == 'post_recheck':
        excluded = set(load(ROOT / 'validation/recheck_summary.json')['excluded_point_ids'])
        rows = [r for r in rows if r['point_id'] not in excluded]
    lookup = {r['point_id']: r for r in rows}
    c, center, samples = area_data()
    cache = {}
    values = {}
    hwdraws = {}
    for r in rows:
        h = r['hardware_id']
        if h not in values:
            x = area_feature(r)
            values[h] = float(x @ center)
            hwdraws[h] = samples @ x
    pairs = read_csv(out / 'strictly_dominating_pairs.csv')
    sensitivity = []
    for pair in pairs:
        a, b = lookup[pair['lat_point_id']], lookup[pair['task_point_id']]
        delta = area_feature(b) - area_feature(a)
        key = tuple(delta)
        if key not in cache:
            draw = samples @ delta
            cache[key] = dict(area_difference_center_mm2=float(delta @ center),
                MC_task_lower_area_fraction=float(np.mean(draw < -1e-12)),
                MC_task_not_higher_area_fraction=float(np.mean(draw <= 1e-12)),
                area_difference_MC_p5_mm2=float(np.quantile(draw, .05)),
                area_difference_MC_p95_mm2=float(np.quantile(draw, .95)))
        same_type = a['memory'].split('_')[0] == b['memory'].split('_')[0]
        result = dict(pair, **cache[key], cross_type=not same_type,
                      scope='secondary_literature_cost', phy_break_even_mm2_per_channel=None,
                      phy_break_even_interval_position=None)
        if same_type:
            standard = a['memory'].split('_')[0]
            index = ('LPDDR5', 'GDDR6', 'HBM2').index(standard) + 3
            channels = delta[index]
            if channels:
                threshold = -float(delta[:3] @ center[:3]) / channels
                thresholds = -(samples[:, :3] @ delta[:3]) / channels
                coefficient = c['A_phy_' + standard]
                result.update(phy_coefficient='A_phy_' + standard,
                    phy_break_even_mm2_per_channel=threshold,
                    phy_lower=coefficient['lower'], phy_upper=coefficient['upper'],
                    phy_break_even_interval_position=('below' if threshold < coefficient['lower'] else
                        'above' if threshold > coefficient['upper'] else 'inside'),
                    phy_break_even_MC_p5=float(np.quantile(thresholds, .05)),
                    phy_break_even_MC_p95=float(np.quantile(thresholds, .95)),
                    task_lower_area_condition='A_phy > threshold' if channels < 0 else 'A_phy < threshold')
            else:
                result['break_even_status'] = 'same_channel_count_PHY_cancels_no_finite_threshold'
        else:
            result['break_even_status'] = 'cross_type_requires_two_PHY_coefficients_no_single_threshold'
        sensitivity.append(result)
    write_csv(out / 'area_sensitivity.csv', sensitivity)
    selections, winners, selected = [], [], {}
    for lmax, smax in BOXES:
        result = dict(Lmax_ms=lmax, Smax_ms=smax, scope='secondary_literature_cost',
                      cross_type_energy_comparable=False)
        pair = {}
        optimum = {}
        for protocol in ('latency_only', 'task_aware'):
            eligible = [r for r in rows if feasible(r, lmax, smax, protocol)]
            if protocol == 'latency_only':
                eligible = [r for r in eligible if abs(float(r['T_s']) - float(r['Tmin_s'])) < 1e-10]
            byhw = {}
            for r in eligible:
                key = (float(r['L_s']), float(r['S_s']), r['point_id'])
                if r['hardware_id'] not in byhw or key < (float(byhw[r['hardware_id']]['L_s']),
                        float(byhw[r['hardware_id']]['S_s']), byhw[r['hardware_id']]['point_id']):
                    byhw[r['hardware_id']] = r
            if not byhw:
                result[protocol + '_point_id'] = None
                continue
            best = min(byhw.values(), key=lambda r: (values[r['hardware_id']], float(r['L_s']), r['point_id']))
            pair[protocol] = best
            selected[best['point_id']] = best
            result.update({protocol + '_' + k: v for k, v in summary(best).items()})
            result[protocol + '_area_center_mm2'] = values[best['hardware_id']]
            choices = sorted(byhw)
            matrix = np.stack([hwdraws[h] for h in choices])
            best_indices = np.argmin(matrix, axis=0)
            optimum[protocol] = np.min(matrix, axis=0)
            for index, count in Counter(best_indices).items():
                winners.append(dict(Lmax_ms=lmax, Smax_ms=smax, protocol=protocol,
                    hardware_id=choices[index], point_id=byhw[choices[index]]['point_id'],
                    MC_selected_fraction=count/2000, scope='secondary_literature_cost'))
        if len(pair) == 2:
            a, b = pair['latency_only'], pair['task_aware']
            diff = hwdraws[b['hardware_id']] - hwdraws[a['hardware_id']]
            result.update(area_difference_center_mm2=values[b['hardware_id']] - values[a['hardware_id']],
                MC_fixed_pair_task_lower_fraction=float(np.mean(diff < -1e-12)),
                MC_reoptimized_task_lower_fraction=float(np.mean(optimum['task_aware'] < optimum['latency_only'] - 1e-12)),
                cross_type=a['memory'].split('_')[0] != b['memory'].split('_')[0])
        selections.append(result)
    write_csv(out / 'selection_comparison_global_area.csv', selections)
    write_csv(out / 'global_area_MC_selection_frequencies.csv', winners)
    write_csv(out / 'global_area_selected_points.csv', selected.values())
    energy = energy_ratios(pairs, lookup, out)
    write_csv(out / 'energy_ratio_same_type.csv', energy)
    write_json(out / 'secondary_status.json', dict(area_pairs=len(sensitivity), boxes=len(selections),
        global_selected_points=len(selected), energy_ratios=len(energy),
        energy_ratio_checks_passed=all(r.get('ratio_cancellation_passed', True) for r in energy),
        cross_type_energy_comparable=False, samples=2000, scope='secondary_literature_cost',
        coefficient_provenance_caution='Micron centers supplied by author; not independently retrieved.'))
    print('Secondary', phase, len(sensitivity), 'area pairs', len(energy), 'ratios', flush=True)


def energy_ratios(pairs, lookup, out):
    wl = Pi05Workload()
    macs = (wl.vlm_totals()[0] + wl.dit_totals_per_request()[0])/2
    c = load(ROOT / 'cost/coefficients.json')['coefficients']
    output = []
    def compare(a, b, role, **context):
        same = a['memory'].split('_')[0] == b['memory'].split('_')[0]
        ta = float(a['steady_dram_GB_per_req']) * 1e9
        tb = float(b['steady_dram_GB_per_req']) * 1e9
        ratio = tb / ta
        result = dict(role=role, baseline_id=a.get('point_id', a['hardware_id'] + '_k1'),
            task_id=b.get('point_id', b['hardware_id'] + '_k' + str(b['dit_stages']) + '_' + str(b['dit_batching'])),
            baseline_memory=a['memory'], task_memory=b['memory'], same_type=same,
            baseline_DRAM_bytes_per_req=ta, task_DRAM_bytes_per_req=tb,
            DRAM_byte_ratio=ratio, MACs_baseline_per_req=macs, MACs_task_per_req=macs,
            MAC_ratio=1., DRAM_energy_ratio_lower=None, DRAM_energy_ratio_center=None,
            DRAM_energy_ratio_upper=None, **context)
        if same:
            e = c['e_dram_' + a['memory'].split('_')[0]]
            for level, label in (('lower', 'lower'), ('value', 'center'), ('upper', 'upper')):
                result['DRAM_energy_ratio_' + label] = (tb * 8 * e[level]) / (ta * 8 * e[level])
            result['ratio_cancellation_passed'] = all(abs(result['DRAM_energy_ratio_' + label] - ratio) < 1e-12
                                                        for label in ('lower', 'center', 'upper'))
            if not result['ratio_cancellation_passed']:
                raise RuntimeError('HARD_STOP_same_type_energy_ratio_cancellation')
        else:
            result['energy_status'] = 'cross_type_energy_ratio_prohibited'
        output.append(result)
    ablations = read_csv(ROOT / 'inputs/paper/k_ablation_summary.csv')
    for hw in sorted({r['hardware_id'] for r in ablations}):
        members = [r for r in ablations if r['hardware_id'] == hw]
        baseline = next(r for r in members if int(r['dit_stages']) == 1)
        for row in members:
            compare(baseline, row, 'same_allocation_k_ablation', hardware_id=hw,
                    k=int(row['dit_stages']), batching=row['dit_batching'])
    seen = set()
    for pair in pairs:
        if (int(pair['Lmax_ms']), int(pair['Smax_ms'])) not in ((200, 100), (250, 150)):
            continue
        identity = pair['lat_point_id'], pair['task_point_id']
        if identity in seen:
            continue
        seen.add(identity)
        compare(lookup[identity[0]], lookup[identity[1]], 'main_example_strict_pair')
    front = read_csv(out / 'pareto_frontier_points.csv')
    for box in ((200, 100), (250, 150)):
        representatives = {}
        for r in front:
            if (int(r['Lmax_ms']), int(r['Smax_ms'])) != box:
                continue
            point = lookup[r['point_id']]
            key = r['protocol'], r['n_cores'], r['BW_peak_GBps']
            rank = (float(point['sram_mb']), float(point['local_kb']), float(point['L_s']), point['point_id'])
            if key not in representatives or rank < representatives[key][0]:
                representatives[key] = rank, point
        lat = [r for k, (_, r) in representatives.items() if k[0] == 'latency_only']
        task = [r for k, (_, r) in representatives.items() if k[0] == 'task_aware']
        for a in lat:
            for b in task:
                identity = a['point_id'], b['point_id']
                if identity not in seen:
                    seen.add(identity)
                    compare(a, b, 'main_example_resource_alternative_not_necessarily_dominating',
                            Lmax_ms=box[0], Smax_ms=box[1])
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('pre_recheck', 'post_recheck'))
    run(parser.parse_args().phase)
