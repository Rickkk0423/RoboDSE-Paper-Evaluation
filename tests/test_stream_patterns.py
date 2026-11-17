import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stream_patterns", ROOT / "vlasim/ramulator_bridge/stream_patterns.py")
patterns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patterns)


@pytest.mark.parametrize("a,b", [(0, 8), (8, 0), (5, 5), (49, 51), (32702, 32834)])
def test_integer_order_exact_counts_and_bounded_discrepancy(a, b):
    order = list(patterns.uniform_order(a, b))
    assert order.count(0) == a and order.count(1) == b
    cumulative = 0
    for i, stream in enumerate(order, 1):
        cumulative += stream == 0
        assert cumulative == i * a // (a + b)


def test_balanced_control_and_skew_preserve_counts():
    assert list(patterns.uniform_order(3, 3)) == [1, 0, 1, 0, 1, 0]
    balanced = patterns.describe_order(patterns.uniform_order(512, 512))
    skew = patterns.describe_order(patterns.skew_order(1024, 1))
    assert balanced["stream_requests"] == skew["stream_requests"] == [512, 512]
    assert balanced["max_cursor_skew_bytes"] == 64
    assert skew["max_cursor_skew_bytes"] > 4096
    assert skew["near_cursor_fraction"]["4096"] < 1


def test_shuffle_is_seeded_exact_and_does_not_touch_global_rng():
    import random
    before = random.getstate()
    a = list(patterns.shuffled_order(1024, 17))
    assert random.getstate() == before
    assert a == list(patterns.shuffled_order(1024, 17))
    assert a != list(patterns.shuffled_order(1024, 29))
    assert a.count(0) == a.count(1) == 512


def test_design_has_48_unique_cases():
    cases = patterns.experiment_cases()
    assert len(cases) == len({c["case"] for c in cases}) == 48
    assert sum(c["group"] == "dense_ratio" for c in cases) == 26
    assert sum(c["group"] == "generator_control" for c in cases) == 6


def test_trace_patterns_preserve_per_stream_addresses(tmp_path, monkeypatch):
    import csv
    monkeypatch.syspath_prepend(str(ROOT / "vlasim/ramulator_bridge"))
    probe_spec = importlib.util.spec_from_file_location("probe_balance", ROOT / "vlasim/ramulator_bridge/probe_balance.py")
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    addresses = []
    for pattern, parameter in (("uniform", 0), ("skew", 16), ("shuffle", 17), ("legacy", 0)):
        path = tmp_path / (pattern + ".csv")
        desc = probe.make_trace(path, dict(size_mib=1, ratio_bp=5000, shift_bytes=4096,
                                         pattern=pattern, parameter=parameter))
        with path.open() as f:
            rows = list(csv.reader(f))
        addresses.append({s: [row[3] for row in rows if row[1] == s] for s in ("vlm", "dit")})
        assert desc["stream_requests"] == [8192, 8192]
    assert all(a == addresses[0] for a in addresses)


@pytest.mark.parametrize("counts", [(0, 0), (-1, 2), (1.5, 2), (True, 2)])
def test_invalid_counts_rejected(counts):
    with pytest.raises(ValueError):
        list(patterns.uniform_order(*counts))
