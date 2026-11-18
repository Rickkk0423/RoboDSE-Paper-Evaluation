"""Three-way selection on frozen candidates, with explicit matched support."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vlasim'))
from v7_common import BOXES, feasible, pareto, read_csv, resource, summary, write_csv
from v7_pareto import classify

ARMS = ('serial', 'no_batching', 'full')
REQUIRED = {(1, True), (2, True), (3, True), (2, False), (3, False)}


def organization(row):
    return int(row['dit_stages']), row['dit_batching'] == 'True'


def allowed(row, arm):
    if row['mode'] == 'serial':
        return True
    return arm == 'full' or (arm == 'no_batching' and
                            (organization(row)[0] == 1 or not organization(row)[1]))


def matched_support(rows):
    groups = defaultdict(set)
    def key(r):
        return r['hardware_id'], r['vlm_cores'], float(r['factor'])
    for r in rows:
        if r['mode'] != 'serial' and r['candidate_source'] == 'retained_search_curve':
            groups[key(r)].add(organization(r))
    complete = {k for k, values in groups.items() if REQUIRED <= values}
    # Serial candidates have no split counterpart; retain them only on common hardware.
    hardware = {k[0] for k in complete}
    selected = [r for r in rows if r['hardware_id'] in hardware and
                (r['mode'] == 'serial' or
                 (r['candidate_source'] == 'retained_search_curve' and key(r) in complete))]
    return selected, dict(total_groups=len(groups), complete_groups=len(complete),
                         common_hardware=len(hardware), retained_rows=len(selected))


def run(out):
    source = ROOT / 'results/v7/inputs/candidate_points.csv'
    audit = ROOT / 'results/v7/validation/recheck_summary.json'
    excluded = set(json.loads(audit.read_text())['excluded_point_ids'])
    rows = [r for r in read_csv(source) if r['point_id'] not in excluded]
    matched, coverage = matched_support(rows)
    out.mkdir(parents=True, exist_ok=False)
    comparisons, fronts, coverage_rows = [], [], []
    for scope, population in [('frozen_retained', rows), ('matched_support', matched)]:
        for eligibility in ('all_v7_eligible', 'refreshed_only'):
            points = [r for r in population if eligibility == 'all_v7_eligible' or
                      r['conditional_status'] == 'refreshed_median_eligible']
            for arm in ARMS:
                pool = [r for r in points if allowed(r, arm)]
                coverage_rows.append(dict(scope=scope, eligibility=eligibility, arm=arm,
                    candidates=len(pool), hardware=len({r['hardware_id'] for r in pool})))
            for lmax, smax in BOXES:
                pools = {a: [r for r in points if allowed(r, a) and feasible(
                    r, lmax, smax, 'latency_only' if a == 'serial' else 'task_aware')]
                    for a in ARMS}
                for sram in (False, True):
                    pf = {a: pareto(pools[a], sram=sram) for a in ARMS}
                    base = dict(scope=scope, eligibility=eligibility, Lmax_ms=lmax,
                                Smax_ms=smax, dimensions='cores_BW_SRAM' if sram else 'cores_BW')
                    for a in ARMS:
                        for r in pf[a]:
                            fronts.append(dict(**base, arm=a, **summary(r)))
                    for a, b in [('serial', 'no_batching'), ('no_batching', 'full'), ('serial', 'full')]:
                        # classify uses 2D vectors; use the same set relation explicitly for 3D.
                        av = {resource(r, sram) for r in pf[a]}
                        bv = {resource(r, sram) for r in pf[b]}
                        from v7_common import dominates
                        relation = ('identical' if av == bv else
                            'lat_infeasible_task_feasible' if not av else
                            'task_strictly_better' if any(dominates(y, x) for y in bv for x in av)
                            else 'task_extends')
                        comparisons.append(dict(**base, baseline=a, alternative=b, relation=relation,
                            both_empty=not av and not bv, baseline_vectors=len(av),
                            alternative_vectors=len(bv), baseline_min_BW=min((v[1] for v in av), default=None),
                            alternative_min_BW=min((v[1] for v in bv), default=None)))
    write_csv(out / 'box_comparisons.csv', comparisons)
    write_csv(out / 'frontier_points.csv', fronts)
    write_csv(out / 'coverage.csv', coverage_rows)
    totals = defaultdict(Counter)
    for r in comparisons:
        key = '|'.join(str(r[k]) for k in ('scope', 'eligibility', 'dimensions', 'baseline', 'alternative'))
        totals[key][r['relation']] += 1
    report = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        recheck_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        excluded_points=len(excluded), matched_coverage=coverage,
        counts=dict(totals), new_hardware_simulations=0, new_task_episodes=0,
        limitations=['Frozen retained search was incumbent-pruned; no global optimality claim.',
            'Matched support balances five organizations at hardware/split/period-factor level, not absolute periods.',
            'Matching conditions on successful retained curves; omitted mappings are not independently evaluated.',
            'Serial uses the V7 serial L<=Smax definition; joint arms use both actual L and S.',
            '2D fronts may trade SRAM; 3D sensitivity is supplied.'])
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'results/v8_no_batching')
    run(parser.parse_args().out)
