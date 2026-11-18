import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vlasim'))
from vlasim.dynamicvla_workload import DynamicVLAWorkload


def profile():
    def op(phase, kind, weights=0):
        return dict(phase=phase, kind=kind, name=kind, m=20, n=64, k=64, repeats=1,
                    flops=163840, weight_elements=weights, weight_bytes=weights*2,
                    input_dtype='torch.bfloat16', output_shape=[1, 20, 64])
    step = [op('dit', 'linear', 4096), op('dit', 'attention_matmul')]
    return dict(checkpoint_config=dict(chunk_size=20, num_steps=10),
                operations=[op('prefix', 'linear', 4096)]+step*10,
                kv_cache=dict(elements=1280))


def test_weight_reuse_and_private_attention():
    wl = DynamicVLAWorkload(profile())
    one = wl.dit_round_ops(1, 1, False, 128, False, 0)
    three = wl.dit_round_ops(3, 1, False, 128, False, 0)
    assert sum(o.weight_bytes for o in one) == sum(o.weight_bytes for o in three)
    assert three[0].flops == 3*one[0].flops
    assert three[1].dram_bytes == 3*one[1].dram_bytes
    assert three[1].util == one[1].util
    assert three[0].util == 3*one[0].util
    assert wl.dit_totals_per_request()[1] == 81920


def test_residency_and_onchip_kv():
    wl = DynamicVLAWorkload(profile())
    ops = wl.dit_round_ops(2, 3, True, 128, False, .5)
    assert sum(o.dram_bytes for o in ops) == 3*4096
    prefix = wl.vlm_ops(False, .85)
    assert sum(o.dram_bytes-o.weight_bytes for o in prefix) == wl.kv_total_bytes


def test_reject_missing_attention_and_varying_steps():
    p = profile()
    p['operations'] = [o for o in p['operations'] if o['kind'] != 'attention_matmul']
    with pytest.raises(ValueError, match='Attention'):
        DynamicVLAWorkload(p)
    p = copy.deepcopy(profile())
    p['operations'][-1]['flops'] = 1
    # deepcopy preserves shared object references in the synthetic fixture.
    p['operations'][-1] = dict(p['operations'][-1], flops=2)
    with pytest.raises(ValueError, match='vary'):
        DynamicVLAWorkload(p)


def test_prefix_spill_is_explicit():
    wl = DynamicVLAWorkload(profile())
    cached = wl.vlm_ops(True, .85, True)
    spilled = wl.vlm_ops(True, .85, False)
    assert spilled[0].dram_bytes-cached[0].dram_bytes == 20*64*4


def test_delivered_trace_covers_all_observed_matrix_operations():
    path = Path(__file__).resolve().parents[1]/'publication/dynamicvla_pilot/profile.json'
    data = json.loads(path.read_text())
    for kind, dispatched in [('linear', 'aten.linear.default'), ('conv2d', 'aten.conv2d.default'),
                             ('attention_matmul', 'aten.matmul.default')]:
        assert sum(o['kind'] == kind for o in data['operations']) == data['dispatched_operations'][dispatched]
    assert data['final_hook_depth'] == 0
    assert data['repeat_max_abs_error'] == data['trace_max_abs_error'] == 0
    wl = DynamicVLAWorkload(data)
    assert len(wl.prefix) == 569
    assert len(wl.step) == 140
    assert wl.c.H == 20 and wl.c.flow_steps == 10


def test_compact_delivery_hashes():
    root = Path(__file__).resolve().parents[1]/'publication/dynamicvla_pilot'
    for name, sha in json.loads((root/'SHA256.json').read_text()).items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == sha, name
