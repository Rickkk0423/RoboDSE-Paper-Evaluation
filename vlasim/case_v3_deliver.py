"""Publish canonical Case v3 outputs while preserving prerequisite history."""
import argparse
import json
from pathlib import Path
import shutil

from case_v3_main import digest, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    repo = args.repo.resolve()
    source = repo / 'results/case_v3_complete'
    target = repo / 'results/case_v3'
    history = target / 'pre_main'
    history.mkdir(exist_ok=False)
    for name in ('status.json', 'ablations.md'):
        shutil.copy2(target / name, history / name)
    names = ('sweep.csv', 'frontier.csv', 'frontier_tolerant.csv', 'ablations.md',
             'compute_report.json', 'selected.csv', 'selected_stability.csv', 'convergence.csv',
             'k_non_improvements.csv', 'native_isolation.csv', 'rule_checks.json',
             'completion_status.json', 'coverage.json', 'experiment_manifest.json',
             'audit.json', 'cross_host_report.json')
    for name in names + tuple(f'ablation_{i}.csv' for i in range(1, 6)):
        shutil.copy2(source / name, target / name)
    shutil.copy2(source / 'status.json', target / 'scan_status.json')
    shutil.copy2(source / 'completion_status.json', target / 'status.json')
    shutil.copy2(repo / 'docs/CASE_V3_FULL_RESULTS.md', source / 'FULL_REPORT.zh.md')
    shutil.copy2(repo / 'docs/CASE_V3_FULL_RESULTS.md', target / 'REPORT.md')
    for path in source.glob('dram_v3_*.json'):
        shutil.copy2(path, target / 'calib' / path.name)
    shutil.copy2(source / 'synthetic_1024.json', target / 'calib/synthetic_1024.json')
    (target / 'raw_evidence').symlink_to('../case_v3_complete', target_is_directory=True)
    shutil.copy2(Path(__file__), source / 'case_v3_deliver.executed.py')
    roots = [source, target]
    roots.extend(repo / ('results/einst/' + name) for name in
                 ('case_v3_p0', 'case_v3_followup', 'case_v3_lpddr_mapping', 'case_v3_mop_isolation'))
    files = sorted({p for root in roots for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                    and p.name != 'delivery_manifest.json'})
    files += [repo / 'docs/CASE_V3_FULL_RESULTS.md']
    hashes = {str(p.relative_to(repo)): digest(p) for p in files}
    payload = dict(files=hashes, file_count=len(hashes), source_sha256=digest(Path(__file__)),
                   scope='Canonical delivery and complete Case v3 evidence, including all158 native runs. Raw source snapshots have separate pinned manifests. Symlinks are not traversed.',
                   authoritative_status='results/case_v3/completion_status.json',
                   frozen_main_status='results/case_v3_complete/status.json',
                   report='docs/CASE_V3_FULL_RESULTS.md')
    write_json(source / 'delivery_manifest.json', payload)
    shutil.copy2(source / 'delivery_manifest.json', target / 'delivery_manifest.json')
    for name, expected in hashes.items():
        if digest(repo / name) != expected:
            raise ValueError('published artifact hash mismatch: ' + name)
    print(json.dumps(dict(verified_files=len(hashes), manifest_sha256=digest(source / 'delivery_manifest.json'))))


if __name__ == '__main__':
    main()
