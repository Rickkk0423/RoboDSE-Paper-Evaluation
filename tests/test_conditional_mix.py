import importlib.util
import io
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("conditional_mix", Path(__file__).resolve().parents[1] / "vlasim/ramulator_bridge/conditional_mix.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def test_predeclared_split_has_unique_cases_and_no_layout_leakage():
    cases = model.experiment_cases()
    assert len(cases) == len({r["case"] for r in cases}) == 62
    assert sum(r["split"] == "train" for r in cases) == 24
    assert all(r["size_mib"] in (1, 4) and r["ratio_pct"] in (25, 50, 75)
               and r["shift_bytes"] != 64 for r in cases if r["split"] == "train")


def training_rows():
    return [dict(split="train", shift_bytes=0, ratio_pct=r, measured_GBps=v)
            for r, v in ((25, 150), (50, 90), (75, 150))]


def test_fit_ignores_heldout_measurements():
    rows = training_rows()
    expected = model.fit_conditions(rows)
    assert model.fit_conditions(rows + [dict(split="heldout_ratio", shift_bytes=0,
                                             ratio_pct=40, measured_GBps=999)]) == expected


def test_ratio_interpolation_and_layout_abstention():
    fit = model.fit_conditions(training_rows())
    assert model.predict(fit, 0, 40) == (114, "supported")
    assert model.predict(fit, 0, 50) == (90, "supported")
    assert model.predict(fit, 64, 50) == (None, "unsupported_layout")
    assert model.predict(fit, 0, 10) == (None, "unsupported_ratio")


def test_failed_prediction_and_abstention_are_not_passes():
    fit = model.fit_conditions(training_rows())
    rows = [dict(split="heldout_ratio", shift_bytes=0, ratio_pct=40, measured_GBps=155),
            dict(split="unsupported_layout", shift_bytes=64, ratio_pct=40, measured_GBps=100)]
    results, groups = model.evaluate(rows, fit, 90)
    assert groups["heldout_ratio"]["gate"] == "failed"
    assert groups["unsupported_layout"]["gate"] == "abstained"
    assert results[1]["within_10pct"] is None


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_fit_rejects_invalid_bandwidth(value):
    rows = training_rows()
    rows[0]["measured_GBps"] = value
    with pytest.raises(ValueError):
        model.fit_conditions(rows)


def test_backend_counter_accounting():
    counter_spec = importlib.util.spec_from_file_location("analyze_layout", Path(__file__).resolve().parents[1] / "vlasim/ramulator_bridge/analyze_layout.py")
    counters = importlib.util.module_from_spec(counter_spec)
    counter_spec.loader.exec_module(counters)
    channel = dict(read_row_hits=8, read_row_misses=1, read_row_conflicts=1,
                   num_read_reqs=10, read_queue_len_avg=2, read_latency=50)
    result = counters.summarize_channels({"memory_system": {"controller": [channel, channel]}})
    assert result["num_read_reqs"] == 20
    assert result["row_conflict_fraction"] == 0.1
    assert result["request_weighted_read_latency_cycles"] == 5
    with pytest.raises(ValueError, match="account for all reads"):
        counters.summarize_channels({"memory_system": {"controller": [dict(channel, num_read_reqs=11)]}})


def test_order_probe_preserves_addresses_and_matches_original_balanced():
    gen_spec = importlib.util.spec_from_file_location("gen_traces", Path(__file__).resolve().parents[1] / "vlasim/ramulator_bridge/gen_traces.py")
    gen = importlib.util.module_from_spec(gen_spec)
    gen_spec.loader.exec_module(gen)
    original, burst1, burst4 = io.StringIO(), io.StringIO(), io.StringIO()
    gen.interleave(original, "vlm", "dit", 640, 640)
    gen.blocked_balanced(burst1, 640, 1)
    gen.blocked_balanced(burst4, 640, 4)
    assert original.getvalue() == burst1.getvalue()
    assert sorted(burst1.getvalue().splitlines()) == sorted(burst4.getvalue().splitlines())
    assert burst1.getvalue() != burst4.getvalue()
    with pytest.raises(ValueError):
        gen.blocked_balanced(io.StringIO(), 640, 0)
