import pytest

from v5_audit import accounting, compare_values


def test_cross_host_nested_absolute_tolerance_and_identities():
    assert not compare_values({'x': [1, None, 'identity']}, {'x': [1+1e-7, None, 'identity']})
    assert compare_values({'x': 1}, {'x': 1+2e-6})
    assert compare_values({'x': 'a'}, {'x': 'b'})
    assert compare_values({'x': [1]}, {'x': [1, 2]})
    assert compare_values({'x': 1}, {'y': 1})
    assert compare_values(True, 1)
    assert compare_values(float('nan'), float('nan'))


def valid_accounting():
    native = dict(accepted=10, completed=10, stream_transactions=[4, 6], logical_bytes=320)
    raw = dict(total_num_read_requests=7, total_num_write_requests=3,
               controller=[dict(num_read_reqs_served=6, num_read_reqs_forwarded=1,
                                num_write_reqs_served=2, num_write_reqs_coalesced=1)])
    return native, raw


def test_native_accounting_includes_forwarded_and_coalesced():
    native, raw = valid_accounting()
    assert accounting(native, raw, 320)


@pytest.mark.parametrize('key,value', [('accepted', 9), ('completed', 9),
                                      ('stream_transactions', [4, 5]), ('logical_bytes', 319)])
def test_accounting_rejects_changed_native_fields(key, value):
    native, raw = valid_accounting()
    native[key] = value
    assert not accounting(native, raw, 320)


def test_accounting_rejects_unreconciled_bytes_and_controller_counts():
    native, raw = valid_accounting()
    assert not accounting(native, raw, 321)
    raw['controller'][0]['num_read_reqs_forwarded'] = 0
    assert not accounting(native, raw, 320)
