"""Independent inventory and hash audit of the completed domain campaign."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vlasim'))
from v7_common import read_csv, write_csv, write_json


def run():
    out = ROOT / 'results/v9_no_batching_domain'
    report = json.loads((out / 'summary.json').read_text())
    configs = read_csv(out / 'configurations.csv')
    candidates = read_csv(out / 'candidate_points.csv')
    byconfig = Counter(r['config_id'] for r in candidates)
    statuses, hashes = {}, 0
    for p in sorted(out.glob('shards/*/runs/*/status.json')):
        value = json.loads(p.read_text())
        assert hashlib.sha256((p.parent / 'requests.npz').read_bytes()).hexdigest() == value['raw_sha256']
        statuses[p.parent.name] = value
        hashes += 1
    rejected = []
    for config in configs:
        value = statuses[config['semantic_id']]
        accepted = [p for p in value['curve'] if p['gate']['pass_gate']]
        assert byconfig[config['config_id']] == len(accepted)
        assert len(value['curve']) == 5
        for point in value['curve']:
            if not point['gate']['pass_gate']:
                rejected.append(dict(**config, factor=point['factor'], gate_json=json.dumps(point['gate'])))
    for p in out.glob('checks960/*.json'):
        value = json.loads(p.read_text())
        assert hashlib.sha256(p.with_suffix('.npz').read_bytes()).hexdigest() == value['raw_sha256']
        hashes += 1
    for rel, sha in json.loads((out / 'input_manifest.json').read_text()).items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel
    assert len(candidates) + len(rejected) == len(configs) * 5
    assert not report['failed_checks']
    write_csv(out / 'excluded_curve_points.csv', rejected)
    result = dict(passed=True, raw_hashes_verified=hashes, configuration_curves_verified=len(configs),
                  evaluated_curve_identities=len(configs)*5, accepted_curve_identities=len(candidates),
                  excluded_curve_identities=len(rejected),
                  excluded_semantic_factors=len({(r['semantic_id'],r['factor']) for r in rejected}),
                  input_hashes_unchanged=True, note='Original periodic gates unchanged; rejected curve points not relaxed.')
    write_json(out / 'independent_audit.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
