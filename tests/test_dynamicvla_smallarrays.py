import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('smallarrays', ROOT/'scripts/run_dynamicvla_smallarrays.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('dim,peak,min_kb', [(16, .512, 2), (32, 2.048, 8), (64, 8.192, 32)])
def test_small_core_physical_resources(dim, peak, min_kb):
    hw = module.make_hardware(dim, 1, 4, 12.8)
    assert hw.peak/1e12 == pytest.approx(peak)
    assert hw.local_min_kb == min_kb
    assert hw.local_kb >= hw.local_min_kb
    assert hw.array_rows == hw.array_cols == dim
    assert hw.dram_bw == 12.8e9


def test_all_allocations_and_ablations_are_retained():
    assert module.mappings(1) == [('serial', 1, 1, True)]
    assert len(module.mappings(2)) == 6
    assert len(module.mappings(4)) == 16
    for split in (1, 2, 3):
        for k in (2, 3):
            assert ('pipelined', split, k, False) in module.mappings(4)
            assert ('pipelined', split, k, True) in module.mappings(4)


@pytest.mark.parametrize('args', [(128, 1, 4, 12.8), (16, 0, 4, 12.8),
                                 (16, 1, 0, 12.8), (16, 1, 4, 0)])
def test_invalid_grid_rejected(args):
    with pytest.raises(ValueError):
        module.make_hardware(*args)


def test_smallarray_delivery_hashes_and_evidence_scope():
    root = ROOT/'publication/dynamicvla_smallarrays'
    for name, sha in json.loads((root/'SHA256.json').read_text()).items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == sha, name
    summary = json.loads((root/'summary.json').read_text())
    assert summary['hardware_identities'] == 81
    assert summary['configurations'] == summary['checks960'] == 621
    assert summary['python_cpp_checks'] == 18
    assert summary['new_ramulator_runs'] == summary['task_episodes'] == 0
    bounds = json.loads((root/'resource_frontiers.json').read_text())
    selected = {b['arm']: b for b in bounds if b['scope'] == 'uncalibrated_peak_sensitivity'
                and (b['Lmax_ms'], b['Smax_ms']) == (200, 100)}
    assert not selected['serial']['vectors']
    assert not selected['no_batching']['vectors']
    assert selected['full']['vectors']
    for box in bounds:
        vectors = box['vectors']
        for v in vectors:
            assert not any(w != v and all(x <= y for x, y in zip(w, v)) for w in vectors)
        for witness in box['witnesses']:
            assert witness['memory_scope'] == box['scope']
            assert float(witness['L_ms']) <= box['Lmax_ms']
            assert float(witness['S_ms']) <= box['Smax_ms']
