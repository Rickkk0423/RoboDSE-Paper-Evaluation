import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('domain', ROOT / 'scripts/run_no_batching_domain.py')
domain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(domain)


def test_mapping_inventory_is_balanced():
    assert domain.mappings(1) == [('serial', 1, 1, True)]
    for cores in (2, 3, 4, 6, 8, 12, 16):
        mappings = domain.mappings(cores)
        assert len(mappings) == 1 + 5 * (cores - 1)
        for split in range(1, cores):
            assert {(k, b) for mode, v, k, b in mappings if mode == 'pipelined' and v == split} == {
                (1, True), (2, True), (3, True), (2, False), (3, False)}


def test_fresh_inventory_covers_576_hardware_identities():
    rows = domain.read_csv(ROOT / 'results/v7/inputs/candidate_points.csv')
    hardware = {r['hardware_id']: r for r in rows}
    assert len(hardware) == 576
    assert sum(len(domain.mappings(int(r['n_cores']))) for r in hardware.values()) == 16416


def test_completed_domain_artifacts():
    import json
    import pytest
    folder = ROOT / 'results/v9_no_batching_domain'
    if not (folder / 'summary.json').exists():
        pytest.skip('Domain campaign not complete')
    report = json.loads((folder / 'summary.json').read_text())
    assert report['publishable'] and report['source_unchanged']
    assert not report['failed_checks']
    configs = domain.read_csv(folder / 'configurations.csv')
    assert len(configs) == len({r['config_id'] for r in configs}) == 16416
    rows = domain.read_csv(folder / 'candidate_points.csv')
    assert len(rows) == len({r['point_id'] for r in rows})
    assert all(r['dit_batching'] == 'False' or int(r['dit_stages']) == 1 or r['mode'] == 'serial'
               for r in rows if domain.allowed(r, 'no_batching'))
    comparisons = domain.read_csv(folder / 'box_comparisons.csv')
    assert len(comparisons) == 22 * 2 * 2 * 3
    assert all(int(r['alternative_feasible']) >= int(r['baseline_feasible']) for r in comparisons)
