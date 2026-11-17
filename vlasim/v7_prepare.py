"""Freeze V7 inputs without restoring or altering frozen V6 deliveries."""
import shutil
from pathlib import Path

from v7_common import ROOT, V6, load, digest, read_csv, write_csv, write_json, preservation


def prepare():
    (ROOT / 'inputs').mkdir(parents=True, exist_ok=True)
    spec = Path('/Users/mr.meeseeks/Downloads/NEXT_STEPS_V7.md')
    target = ROOT / 'NEXT_STEPS_V7.md'
    if target.exists() and digest(target) != digest(spec):
        raise RuntimeError('Frozen V7 input specification changed')
    shutil.copy2(spec, target)
    write_json(ROOT / 'inputs/preservation_initial.json', preservation(True))
    rows = read_csv(V6 / 'paper/candidate_points.csv')
    selection = load(V6 / 'repair_selection.json')['tiers']
    for row in rows:
        if row['memory'] == 'GDDR6_c36' or float(row['eta_seq']) < .8:
            raise RuntimeError('Ineligible tier in V6 primary candidates')
        if row['curve_gate'] != 'True':
            raise RuntimeError('Nonpassing curve in primary candidates')
        row['conditional_status'] = ('conditional_norefresh' if row['memory'] in
                                     ('GDDR6_c16', 'GDDR6_c24') else 'refreshed_median_eligible')
        if row['memory'] in selection and row['conditional_status'] == 'conditional_norefresh':
            row['eligibility_note'] = 'median gate only; not all-grain or refreshed-device validation'
    write_csv(ROOT / 'inputs/candidate_points.csv', rows)
    for name in ('calibration.json', 'band/quantiles.json', 'paper/k_ablation_summary.csv',
                 'cost/coefficients.json', 'cost/draws.npz'):
        destination = ROOT / 'inputs' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(V6 / name, destination)
    write_json(ROOT / 'inputs/manifest.json', dict(candidates=len(rows),
        source=str(V6 / 'paper/candidate_points.csv'),
        source_sha256=digest(V6 / 'paper/candidate_points.csv'),
        spec_sha256=digest(target), source_sha256_implementation=digest(__file__),
        scope='Frozen retained V6 candidates, no new DSE, all tied-resource designs retained',
        hashes={str(p.relative_to(ROOT / 'inputs')): digest(p) for p in (ROOT / 'inputs').rglob('*')
                if p.is_file() and p.name != 'manifest.json'}))
    print('Prepared V7', len(rows), 'retained candidates', flush=True)


if __name__ == '__main__':
    prepare()
