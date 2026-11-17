import json

import numpy as np
import yaml

from v4_replay_audit import acceptance, audit, sha


def test_every_stream_is_a_hard_gate():
    result = acceptance([0] * 20 + [11], complete=True,
                        coverage_complete=True, integrity_ok=True)
    assert result['mean_absolute_error_pct'] < 5
    assert not result['numerical_thresholds_pass']
    assert not result['passed']


def test_mean_is_a_separate_hard_gate():
    assert not acceptance([6, 6], complete=True, coverage_complete=True,
                          integrity_ok=True)['passed']


def test_missing_coverage_or_integrity_cannot_pass():
    kwargs = dict(complete=True, coverage_complete=True, integrity_ok=True)
    assert acceptance([1, 2], **kwargs)['passed']
    for key in kwargs:
        assert not acceptance([1, 2], **{**kwargs, key: False})['passed']
    assert not acceptance([], **kwargs)['passed']


def test_audit_completed_evidence_and_detect_trace_corruption(tmp_path):
    inputs, native, out = (tmp_path / p for p in ('inputs', 'native', 'out'))
    inputs.mkdir()
    native.mkdir()
    trace = inputs / 'test.npz'
    np.savez(trace, write=np.array([0, 1], dtype=np.uint8))
    window = dict(id='test', case='case', memory='M-H256', window='W1', launch='open',
                  bg=False, bytes_by_stream=[128, 0], trace=trace.name, trace_sha256=sha(trace))
    pinned = dict(source_manifest_sha256='source', library_sha256='bridge', memory_library_sha256='memory')
    manifest = dict(windows=[window], cases=[dict(name='case', calibration=dict(backend_metadata=pinned))],
                    unavailable=[])
    (inputs / 'manifest.json').write_text(json.dumps(manifest))
    identity = dict(source_manifest_sha256='source', bridge_sha256='bridge', memory_sha256='memory')
    for i in range(8):
        shard = native / f'shard_{i}'
        shard.mkdir()
        sources = shard / 'executed_sources'
        sources.mkdir()
        (sources / 'runner.py').write_text('frozen')
        sm = dict(input_manifest_sha256=sha(inputs / 'manifest.json'), shard=i, shards=8,
                  source_hashes={'runner.py': sha(sources / 'runner.py')}, cases=[window] if i == 0 else [])
        (shard / 'manifest.json').write_text(json.dumps(sm))
        (shard / 'completed.json').write_text(json.dumps(dict(cases=len(sm['cases']),
            manifest_sha256=sha(shard / 'manifest.json'))))
    first = native / 'shard_0'
    (first / 'test.yaml').write_text('native config')
    metric = dict(stream='vlm', actual_duration_ns=100, predicted_duration_ns=100,
                  signed_error_pct=0, absolute_error_pct=0)
    result = dict(window=window, backend_identity=identity, yaml_sha256=sha(first / 'test.yaml'),
        native=dict(accepted=4, completed=4, stream_transactions=[4, 0], logical_bytes=128),
        metrics=[metric], total_over_seq_reference=1)
    (first / 'test.json').write_text(json.dumps(result))
    counters = dict(num_read_reqs_served=2, num_write_reqs_served=2,
                    num_read_reqs_forwarded=0, num_write_reqs_coalesced=0)
    (first / 'test_stats.yaml').write_text(yaml.safe_dump(dict(memory_system=dict(
        total_num_read_requests=2, total_num_write_requests=2, controller=[counters]))))
    assert audit(inputs, native, out)['passed']
    np.savez(trace, write=np.array([0, 0], dtype=np.uint8))
    status = audit(inputs, native, out)
    assert not status['passed']
    assert any('trace hash differs' in s for s in status['integrity_issues'])
    assert any('accounting differs' in s for s in status['integrity_issues'])
