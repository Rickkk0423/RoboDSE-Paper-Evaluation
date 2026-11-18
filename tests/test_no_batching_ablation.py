import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('no_batching', Path(__file__).resolve().parents[1] / 'scripts/ablate_no_batching.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(k=1, batch=True, mode='pipelined', hw='a', factor='1.0'):
    return dict(dit_stages=str(k), dit_batching=str(batch), mode=mode,
                hardware_id=hw, vlm_cores='2', factor=factor,
                candidate_source='retained_search_curve')


def test_no_batching_keeps_k1_and_serial():
    assert module.allowed(row(), 'no_batching')
    assert module.allowed(row(mode='serial'), 'no_batching')
    assert module.allowed(row(3, False), 'no_batching')
    assert not module.allowed(row(2, True), 'no_batching')
    assert not module.allowed(row(), 'serial')


def test_matched_support_requires_all_five_organizations():
    complete = [row(k, b) for k, b in module.REQUIRED]
    rows = complete + [row(mode='serial'), row(hw='b'), row(factor='1.1')]
    matched, audit = module.matched_support(rows)
    assert len(matched) == 6
    assert audit['complete_groups'] == 1
    assert module.matched_support(complete[:-1])[0] == []


def test_supplemental_controls_cannot_fill_missing_search_support():
    rows = [row(k, b) for k, b in module.REQUIRED]
    rows[-1]['candidate_source'] = 'required_unbatched_same_split_control'
    assert module.matched_support(rows)[0] == []
