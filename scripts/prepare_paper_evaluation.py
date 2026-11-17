"""Prepare bounded task projections without changing frozen V7 evidence."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vlasim'))
from analysis.task_report import TaskGrid


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(line for line in stream if not line.startswith('#')))


def write(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    out = ROOT / 'results/v8_eval_prep'
    out.mkdir(exist_ok=False)
    grid_path = ROOT / 'vlasim/data/libero_dynamic_L_S.csv'
    candidates_path = ROOT / 'results/v7/inputs/candidate_points.csv'
    ablation_path = ROOT / 'results/v7/paper/figdata/F2_k_ablation.csv'
    grid = TaskGrid(grid_path)
    projected = []
    for row in read(candidates_path):
        l, s = float(row['L_s']) * 1000, float(row['S_s']) * 1000
        lookup = grid.lookup(l, s)
        projected.append(dict(point_id=row['point_id'], hardware_id=row['hardware_id'],
            memory=row['memory'], n_cores=int(row['n_cores']), BW_GBps=float(row['actual_peak_GBps']),
            shared_MB=float(row['sram_mb']), private_KB=float(row['local_kb']),
            mode=row['mode'], k=int(row['dit_stages']), batching=row['dit_batching'],
            factor=float(row['factor']) if row['factor'] else None,
            L_ms=l, S_ms=s, conditional_status=row['conditional_status'],
            coverage=lookup['status'], estimated_mean_SR_pct=(100 * lookup['valid_only']
                if lookup['valid_only'] is not None else None)))
    write(out / 'candidate_projection.csv', projected)
    controls = []
    for row in read(ablation_path):
        lookup = grid.lookup(float(row['L_ms']), float(row['S_ms']))
        controls.append(dict(row, estimated_mean_SR_pct=(100 * lookup['valid_only']
                            if lookup['valid_only'] is not None else None), coverage=lookup['status']))
    write(out / 'batching_projection.csv', controls)
    # Select the true min-L serial baseline before checking coverage: never replace
    # an uncovered faster baseline with a slower covered design to manufacture gain.
    groups = {}
    for row in projected:
        if row['conditional_status'] == 'refreshed_median_eligible':
            groups.setdefault(row['hardware_id'], []).append(row)
    comparisons = []
    for hardware, rows in sorted(groups.items()):
        serial = [r for r in rows if r['mode'] == 'serial']
        covered = [r for r in rows if r['estimated_mean_SR_pct'] is not None]
        if not serial or not covered:
            continue
        baseline = min(serial, key=lambda r: (r['L_ms'], r['S_ms'], r['point_id']))
        selected = max(covered, key=lambda r: (r['estimated_mean_SR_pct'], -r['L_ms']))
        eligible = baseline['estimated_mean_SR_pct'] is not None
        comparisons.append(dict(hardware_id=hardware, baseline_id=baseline['point_id'],
            baseline_L_ms=baseline['L_ms'], baseline_S_ms=baseline['S_ms'],
            baseline_SR_pct=baseline['estimated_mean_SR_pct'], selected_id=selected['point_id'],
            selected_L_ms=selected['L_ms'], selected_S_ms=selected['S_ms'],
            selected_SR_pct=selected['estimated_mean_SR_pct'],
            estimated_gain_pp=(selected['estimated_mean_SR_pct'] - baseline['estimated_mean_SR_pct']
                               if eligible else None),
            status='descriptive_comparison' if eligible else 'baseline_outside_hull_no_gain_claim'))
    write(out / 'same_hardware_comparison.csv', comparisons)
    summary = dict(scope='aggregate_grid_interpolation_diagnostic_not_closed_loop_validation',
        grid_rows=len(grid.points), candidates=len(projected),
        inside_hull=sum(r['estimated_mean_SR_pct'] is not None for r in projected),
        outside_hull=sum(r['estimated_mean_SR_pct'] is None for r in projected),
        task_episodes_run=0, baseline='min_L_serial_then_min_S_per_exact_hardware',
        H16_model_identity='author_attribution_not_verified_by_legacy_CSV_metadata',
        uncertainty='No per-speed denominators, no binomial CI, no final hardware recommendation',
        inputs_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (grid_path, candidates_path, ablation_path)})
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
