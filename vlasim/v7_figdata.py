"""F1-F6 publication data with declared scope, plus one rough PNG preview."""
import argparse
from collections import defaultdict
import numpy as np

from v7_common import (ROOT, candidates, read_csv, write_csv, write_json, load, summary,
                       truth, resource)


def ls_frontier(rows):
    ordered = sorted(rows, key=lambda r: (float(r['L_s']), float(r['S_s']), r['point_id']))
    best = float('inf')
    result = []
    for row in ordered:
        s = float(row['S_s'])
        if s < best - 1e-12:
            result.append(row)
            best = s
    return result


def ablation_rows():
    rows = read_csv(ROOT / 'inputs/paper/k_ablation_summary.csv')
    rows = [r for r in rows if (r['memory'], int(r['n_cores'])) in
            {('LPDDR5_c8', 4), ('LPDDR5_c8', 8), ('HBM2_c32', 4)}]
    for i, row in enumerate(rows):
        row.update(point_id=f'v7ab{i:02d}', T_s=row['Tmin_s'],
                   conditional_status='refreshed_median_eligible')
    return rows


def run(phase='pre_recheck'):
    base = ROOT / ('paper/pre_recheck' if phase == 'pre_recheck' else 'paper')
    out = base / 'figdata'
    out.mkdir(parents=True, exist_ok=True)
    rows = candidates()
    if phase == 'post_recheck':
        excluded = set(load(ROOT / 'validation/recheck_summary.json')['excluded_point_ids'])
        rows = [r for r in rows if r['point_id'] not in excluded]
    groups = defaultdict(list)
    for r in rows:
        category = ('serial' if r['mode'] == 'serial' else
                    'k' + r['dit_stages'] + ('_batched' if truth(r['dit_batching']) else '_unbatched'))
        groups[r['memory'], category].append(r)
    f1 = []
    for (memory, category), values in sorted(groups.items()):
        for r in ls_frontier(values):
            f1.append(dict(**summary(r), mapping_class=category, Box_Lmax_ms=200, Box_Smax_ms=100))
    write_csv(out / 'F1_LS_frontiers.csv', f1,
        'source=results/v7/inputs/candidate_points.csv; primary retained per-memory/mapping L-S frontier; conditional_norefresh flagged; Box200/100.')
    f2 = []
    for r in ablation_rows():
        steady_dit = float(r['steady_dit_GB_per_req'])
        total = float(r['steady_dram_GB_per_req'])
        f2.append(dict(**summary(r), Tmin_ms=float(r['Tmin_s']) * 1000,
            DiT_GB_per_req=steady_dit, VLM_GB_per_req=total-steady_dit, DRAM_GB_per_req=total,
            full_run_DiT_GB_per_req=float(r['dit_GB_per_req']),
            round_duration_ms=float(r['round_duration_s']) * 1000,
            round_compute_ms=float(r['round_compute_s']) * 1000,
            round_exposed_memory_ms=float(r['round_exposed_memory_s']) * 1000,
            round_wait_ms=float(r['round_wait_before_s']) * 1000,
            round_cycle_ms=(float(r['round_duration_s']) + float(r['round_wait_before_s'])) * 1000,
            steady_DiT_busy=float(r['steady_dit_busy']),
            traffic_scope='steady measured bandwidth*period; full-run drain traffic separately available',
            allocation_scope='same physical HW and VLM/DiT allocation within each hardware across five controls'))
    if len(f2) != 15:
        raise RuntimeError('F2 requires three hardware identities times five controls')
    write_csv(out / 'F2_k_ablation.csv', f2,
        'source=results/v7/inputs/paper/k_ablation_summary.csv; primary same-allocation controls; refreshed LPDDR5/HBM2, no NoRefresh points;480-request baseline metrics.')
    write_csv(out / 'F5_DRAM_traffic_by_k.csv', f2,
        'source=F2_k_ablation.csv; primary steady VLM/DiT bytes per request; same-type traffic ratios only; no cross-type energy comparison.')
    f3 = read_csv(base / 'F3_all_feasible_points.csv')
    write_csv(out / 'F3_resource_plane.csv', f3,
        'source=pareto_frontier_points.csv and inputs/candidate_points.csv; primary all feasible identities for Box200/100 and250/150; on_frontier and protocol flags; conditional_norefresh flagged.')
    write_csv(out / 'F3_strict_dominance_arrows.csv', read_csv(base / 'strictly_dominating_pairs.csv'),
        'source=strictly_dominating_pairs.csv; primary arrow task->lat with strictly lower resource vector; filter main Boxes for display; conditional flagged.')
    byresource = defaultdict(list)
    for r in rows:
        byresource[resource(r)].append(r)
    allcores = sorted({resource(r)[0] for r in rows})
    allbw = sorted({resource(r)[1] for r in rows})
    f4 = []
    for s in (50, 75, 100, 150):
        for bw in allbw:
            for n in allcores:
                choices = [r for r in byresource[n, bw] if float(r['S_s']) * 1000 <= s + 1e-9]
                if choices:
                    r = min(choices, key=lambda r: (float(r['L_s']), float(r['S_s']),
                        float(r['sram_mb']), float(r['local_kb']), r['point_id']))
                    category = 'serial' if r['mode'] == 'serial' else 'k' + r['dit_stages']
                    f4.append(dict(S_target_ms=s, mapping=category, **summary(r)))
                else:
                    f4.append(dict(S_target_ms=s, BW_peak_GBps=bw, n_cores=n, mapping='infeasible',
                                   point_id=None, L_ms=None, S_ms=None))
    write_csv(out / 'F4_best_mapping_grid.csv', f4,
        'source=inputs/candidate_points.csv; primary minimum retained L subject to S<=target; tie L,S,SRAM,id; discrete grid and pruning retained; conditional_norefresh flagged.')
    write_csv(out / 'F6_area_sensitivity.csv', read_csv(base / 'area_sensitivity.csv'),
        'source=area_sensitivity.csv; secondary_literature_cost; same-type PHY thresholds and interval positions; cross_type pairs have no single PHY break-even; conditional flags retained.')
    manifest = dict(phase=phase, F1=len(f1), F2=len(f2), F3=len(f3), F4=len(f4), F5=len(f2),
                    F6=len(read_csv(base / 'area_sensitivity.csv')),
                    final_styled_figures_created=False, scope='CSV publication data plus rough preview only')
    write_json(base / 'figdata_status.json', manifest)


def preview():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image
    data = read_csv(ROOT / 'paper/figdata/F3_resource_plane.csv')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), constrained_layout=True)
    colors = {'refreshed_median_eligible': '#246f91', 'conditional_norefresh': '#c14c36'}
    for ax, box in zip(axes, ((200, 100), (250, 150))):
        selected = [r for r in data if (int(r['Lmax_ms']), int(r['Smax_ms'])) == box]
        unique = {(r['BW_peak_GBps'], r['n_cores']) for r in selected}
        ax.scatter([float(x) for x, y in unique], [int(y) for x, y in unique], s=18,
                   color='#c6cbca', label='All feasible resources')
        for protocol, marker in (('latency_only', 's'), ('task_aware', 'o')):
            for status, color in colors.items():
                values = {(r['BW_peak_GBps'], r['n_cores']) for r in selected
                          if r['protocol'] == protocol and truth(r['on_frontier']) and r['conditional_status'] == status}
                if values:
                    ax.scatter([float(x) for x, y in values], [int(y) for x, y in values],
                        s=65, marker=marker, facecolors='none' if protocol == 'latency_only' else color,
                        edgecolors=color, label=protocol + (' NoRefresh' if status == 'conditional_norefresh' else ''))
        ax.set(title=f'Box({box[0]}, {box[1]}) ms', xlabel='Peak DRAM bandwidth (GB/s)', ylabel='Cores')
        ax.grid(alpha=.18)
        ax.legend(fontsize=7)
    path = ROOT / 'paper/preview.png'
    fig.suptitle('V7 resource Pareto - rough data preview', fontsize=12)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    image = np.asarray(Image.open(path).convert('RGB'))
    nonblank = float(np.mean(np.any(image < 240, axis=-1)))
    if nonblank < .01:
        raise RuntimeError('Blank preview PNG')
    write_json(ROOT / 'paper/preview_QA.json', dict(nonblank_fraction=nonblank,
        width=int(image.shape[1]), height=int(image.shape[0]), nonblank_passed=True,
        visual_inspection=False, limitation='Image-view tool unavailable; automated nonblank check only.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('pre_recheck', 'post_recheck', 'preview'))
    arg = parser.parse_args().phase
    preview() if arg == 'preview' else run(arg)
