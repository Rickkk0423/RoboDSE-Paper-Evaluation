"""Exact resource Pareto comparisons, retaining every resource-equivalent design."""
import argparse
from collections import Counter, defaultdict
import json

from v7_common import (ROOT, BOXES, candidates, resource, dominates, feasible, pareto,
                       summary, write_csv, write_json, load)


def classify(lat, task):
    a, b = {resource(r) for r in lat}, {resource(r) for r in task}
    if not a and b:
        return 'lat_infeasible_task_feasible'
    if a == b:
        return 'identical'
    if any(dominates(y, x) for y in b for x in a):
        return 'task_strictly_better'
    if b - a:
        return 'task_extends'
    raise RuntimeError('Relation outside specification: latency frontier improves on task frontier')


def run(phase='pre_recheck'):
    points = candidates()
    excluded = set()
    if phase == 'post_recheck':
        excluded = set(load(ROOT / 'validation/recheck_summary.json')['excluded_point_ids'])
        points = [r for r in points if r['point_id'] not in excluded]
    out = ROOT / ('paper/pre_recheck' if phase == 'pre_recheck' else 'paper')
    out.mkdir(parents=True, exist_ok=True)
    comparisons, fronts, pairs, bandwidth, cores, sensitivity = [], [], [], [], [], []
    f3 = []
    allcores = sorted({int(r['n_cores']) for r in points})
    allbw = sorted({float(r['actual_peak_GBps']) for r in points})
    for lmax, smax in BOXES:
        eligible = {p: [r for r in points if feasible(r, lmax, smax, p)]
                    for p in ('latency_only', 'task_aware')}
        pf = {p: pareto(rows) for p, rows in eligible.items()}
        relation = classify(pf['latency_only'], pf['task_aware'])
        comparisons.append(dict(Lmax_ms=lmax, Smax_ms=smax, relation=relation,
            P_lat=json.dumps([summary(r) for r in pf['latency_only']], separators=(',', ':')),
            P_task=json.dumps([summary(r) for r in pf['task_aware']], separators=(',', ':')),
            latency_points=len(pf['latency_only']), task_points=len(pf['task_aware']),
            latency_resource_vectors=len({resource(r) for r in pf['latency_only']}),
            task_resource_vectors=len({resource(r) for r in pf['task_aware']}),
            equality_scope='resource-vector sets; all distinct tied designs retained separately',
            phase=phase, excluded_recheck_points=len(excluded)))
        for protocol, values in pf.items():
            for row in values:
                fronts.append(dict(Lmax_ms=lmax, Smax_ms=smax, protocol=protocol, **summary(row)))
            third = pareto(eligible[protocol], sram=True)
            before = {r['point_id'] for r in values}
            after = {r['point_id'] for r in third}
            sensitivity.append(dict(Lmax_ms=lmax, Smax_ms=smax, protocol=protocol,
                dimensions_2D='cores,peak_BW', dimensions_3D='cores,peak_BW,total_shared_plus_private_SRAM_MB',
                two_dimensional_points=len(before), three_dimensional_points=len(after),
                removed_by_SRAM_dimension=len(before-after), added_by_SRAM_dimension=len(after-before),
                two_dimensional_resource_vectors=len({resource(r) for r in values}),
                three_dimensional_projected_resource_vectors=len({resource(r) for r in third}),
                newly_exposed_2D_resource_vectors=len({resource(r) for r in third} - {resource(r) for r in values}),
                dominance_changed=before != after,
                separate_shared_private_reported=True))
        for task in pf['task_aware']:
            for lat in pf['latency_only']:
                if dominates(resource(task), resource(lat)):
                    pairs.append(dict(Lmax_ms=lmax, Smax_ms=smax,
                        task_point_id=task['point_id'], lat_point_id=lat['point_id'],
                        task_cores=resource(task)[0], lat_cores=resource(lat)[0],
                        task_BW_GBps=resource(task)[1], lat_BW_GBps=resource(lat)[1],
                        bandwidth_ratio=resource(task)[1]/resource(lat)[1],
                        core_ratio=resource(task)[0]/resource(lat)[0],
                        strict_dominance_survives_total_SRAM=dominates(resource(task, True), resource(lat, True)),
                        task_total_SRAM_MB=resource(task, True)[2], lat_total_SRAM_MB=resource(lat, True)[2],
                        conditional_status=task['conditional_status']))
        for n in allcores:
            a = [resource(r)[1] for r in pf['latency_only'] if resource(r)[0] == n]
            b = [resource(r)[1] for r in pf['task_aware'] if resource(r)[0] == n]
            bandwidth.append(dict(Lmax_ms=lmax, Smax_ms=smax, n_cores=n,
                BW_lat_GBps=min(a) if a else None, BW_task_GBps=min(b) if b else None,
                BW_task_over_lat=min(b)/min(a) if a and b else None))
        for bw in allbw:
            a = [resource(r)[0] for r in pf['latency_only'] if resource(r)[1] == bw]
            b = [resource(r)[0] for r in pf['task_aware'] if resource(r)[1] == bw]
            cores.append(dict(Lmax_ms=lmax, Smax_ms=smax, BW_peak_GBps=bw,
                cores_lat=min(a) if a else None, cores_task=min(b) if b else None,
                cores_task_over_lat=min(b)/min(a) if a and b else None))
        if (lmax, smax) in ((200, 100), (250, 150)):
            for protocol, values in eligible.items():
                frontier_ids = {r['point_id'] for r in pf[protocol]}
                for row in values:
                    f3.append(dict(Lmax_ms=lmax, Smax_ms=smax, protocol=protocol,
                        on_frontier=row['point_id'] in frontier_ids, **summary(row)))
    write_csv(out / 'pareto_comparison.csv', comparisons)
    write_csv(out / 'pareto_frontier_points.csv', fronts)
    write_csv(out / 'strictly_dominating_pairs.csv', pairs)
    write_csv(out / 'bandwidth_savings.csv', bandwidth)
    write_csv(out / 'core_savings.csv', cores)
    write_csv(out / 'SRAM_dominance_sensitivity.csv', sensitivity)
    write_csv(out / 'F3_all_feasible_points.csv', f3)
    write_json(out / 'pareto_status.json', dict(phase=phase, boxes=len(comparisons),
        classifications=dict(Counter(r['relation'] for r in comparisons)),
        frontier_designs=len({r['point_id'] for r in fronts}),
        strict_pairs=len(pairs), strict_task_points=len({r['task_point_id'] for r in pairs}),
        F3_designs=len({r['point_id'] for r in f3}), retained_candidates=len(points),
        same_resource_ties='All mappings, periods and SRAM identities retained; no arbitrary representative pruning.',
        SRAM_changes_boxes=len({(r['Lmax_ms'], r['Smax_ms']) for r in sensitivity if r['dominance_changed']})))
    print('Pareto', phase, len(fronts), 'memberships', len(pairs), 'strict pairs', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('pre_recheck', 'post_recheck'))
    run(parser.parse_args().phase)
