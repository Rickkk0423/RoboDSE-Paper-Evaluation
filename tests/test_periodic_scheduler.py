from collections import defaultdict
from dataclasses import replace
from types import SimpleNamespace

import pytest

from vlasim import HWConfig, MapConfig, Simulator
from vlasim.workload import Op


class TinyWorkload:
    c = SimpleNamespace(flow_steps=6, w_bytes=2, dit_layers=1)
    dit_layer_params = 1
    vlm_act_bytes = 1
    kv_total_bytes = 1

    def vlm_ops(self, *args):
        return [Op("vlm", 1, 1, 4, "vlm", 3)]

    def dit_round_ops(self, batch, steps, *args):
        return [Op("dit_linear", steps, 1, 2 * steps, "dit", steps)]


def compute(op, group, peak, hw):
    return 0.04 if group == "vlm" else 0.01 * op.flops


def run(mp, n=30, warmup=4, **kwargs):
    return Simulator(HWConfig(n_cores=4, dram_bw=1e6), mp,
                     TinyWorkload(), compute_time_fn=compute).run(
                         n, warmup, **kwargs)


@pytest.mark.parametrize("mode", ["serial", "pipelined"])
@pytest.mark.parametrize("k", [1, 2, 3])
def test_periodic_order_and_stable_completions(mode, k):
    period = 0.3
    mp = MapConfig(mode=mode, vlm_launch="periodic", launch_period_s=period,
                   dit_stages=k)
    result = run(mp, diagnostics=True)
    effective_k = k if mode == "pipelined" else 1
    rows = result["requests"]
    assert len(rows) == 30
    for i, row in enumerate(rows):
        assert row["obs_s"] == i * period
        assert row["vlm_start_s"] == pytest.approx(row["obs_s"])
        assert row["vlm_end_s"] - row["vlm_start_s"] == pytest.approx(0.04)
        assert row["L_s"] == pytest.approx(row["done_s"] - row["obs_s"])
        assert row["done_s"] >= row["vlm_end_s"]
    assert all(a["done_s"] < b["done_s"] for a, b in zip(rows, rows[1:]))
    for row in rows:
        if row["steady_state"]:
            assert row["S_s"] == pytest.approx(period, abs=1e-12)
    rounds = result["dit_rounds"]
    assert sum(r["tail_drain"] for r in rounds) == effective_k - 1
    for i, r in enumerate(rounds[:30]):
        assert r["stage_request_ids"] == [i-s if i >= s else None
                                            for s in range(effective_k)]
        assert r["start_s"] >= rows[i]["vlm_end_s"]
    assert result["vlm_queue"]["max_length"] == 1


@pytest.mark.parametrize("mode", ["serial", "pipelined"])
def test_overload_retains_every_observation_and_includes_queue_wait(mode):
    mp = MapConfig(mode=mode, vlm_launch="periodic", launch_period_s=0.005,
                   dit_stages=3, vlm_queue_max=1)
    result = run(mp, diagnostics=True)
    rows = result["requests"]
    assert [r["request_id"] for r in rows] == list(range(30))
    assert result["vlm_queue"]["max_length"] > 10
    assert result["vlm_queue"]["steady_max_length"] > 1
    assert result["vlm_queue"]["steady_mean_length"] > 0
    assert rows[10]["vlm_wait_s"] > rows[5]["vlm_wait_s"] > 0
    for row in rows:
        assert row["L_s"] == pytest.approx(row["vlm_wait_s"]
                                           + row["done_s"] - row["vlm_start_s"])


@pytest.mark.parametrize("k", [2, 3])
def test_no_timeout_or_advancement_before_next_arrival(k):
    mp = MapConfig(vlm_launch="periodic", launch_period_s=0.5,
                   dit_stages=k, max_wait=0.0)
    result = run(mp, diagnostics=True)
    other = run(replace(mp, max_wait=1000), diagnostics=True)
    assert result == other
    rounds = result["dit_rounds"]
    assert len(rounds) == 30 + k - 1
    assert rounds[1]["start_s"] == pytest.approx(0.54)
    assert rounds[1]["wait_before_s"] > 0.1
    assert all(r["stage_request_ids"][0] is not None
               for r in rounds if not r["tail_drain"])


def test_default_jit_is_unchanged_by_optional_instrumentation():
    mp = MapConfig(dit_stages=3)
    plain = run(mp)
    detailed = run(mp, diagnostics=True, record=True)
    assert "requests" not in plain and "memory_segments" not in plain
    assert plain == {key: detailed[key] for key in plain}
    assert run(replace(mp, vlm_launch="jit", jit_freeze_after=None)) == plain
    # The unfrozen legacy scheduler advances occupied stages on the timeout.
    slow = replace(mp, max_wait=0, vlm_launch="eager")
    long_compute = lambda op, group, peak, hw: 0.5 if group == "vlm" else 0.01
    legacy = Simulator(HWConfig(), slow, TinyWorkload(),
                       compute_time_fn=long_compute).run(30, 4, diagnostics=True)
    assert len(legacy["dit_rounds"]) > 30 + 3 - 1


def test_jit_predictors_freeze_at_first_n_sample_means():
    base = MapConfig(dit_stages=3)
    reference = run(base, diagnostics=True)
    result = run(replace(base, jit_freeze_after=5), diagnostics=True)
    p = result["jit_predictor"]
    assert p["enabled"] and p["frozen"]
    assert p["sample_counts"] == {"vlm": 5, "round": 5}
    rows = reference["requests"][:5]
    assert p["vlm_reference_s"] == pytest.approx(
        sum(r["vlm_end_s"] - r["vlm_start_s"] for r in rows) / 5)
    assert p["round_reference_s"] == pytest.approx(
        sum(r["duration_s"] for r in reference["dit_rounds"][:5]) / 5)
    longer = run(replace(base, jit_freeze_after=5), n=60, diagnostics=True)
    assert longer["jit_predictor"] == p
    incomplete = run(replace(base, jit_freeze_after=100), diagnostics=True)
    assert not incomplete["jit_predictor"]["frozen"]
    assert incomplete["jit_predictor"]["sample_counts"]["vlm"] == 30


def test_memory_segments_reconcile_op_progress_bytes_and_unchanged_timing():
    mp = MapConfig(dit_stages=3)
    hw = HWConfig(n_cores=4, dram_bw=100)
    def simulate(record):
        return Simulator(hw, mp, TinyWorkload(), compute_time_fn=compute).run(
            30, 4, record=record, diagnostics=True)
    result = simulate(True)
    plain = simulate(False)
    assert plain == {key: result[key] for key in plain}
    segments = result["memory_segments"]
    grouped = defaultdict(list)
    for seg in segments:
        assert seg["end_s"] >= seg["start_s"]
        assert seg["op_fraction_end"] >= seg["op_fraction_start"]
        assert seg["dram_bytes"] == pytest.approx(seg["op_total_dram_bytes"] * (
            seg["op_fraction_end"] - seg["op_fraction_start"]))
        grouped[seg["group"], seg["op_name"], seg["request_ids"]].append(seg)
    assert any(len(parts) > 1 for parts in grouped.values())
    assert sum(s["dram_bytes"] for s in segments) == pytest.approx(
        result["dram_GB_per_req"] * 30 * 1e9)
    assert sum(s["weight_bytes"] for s in segments) == pytest.approx(
        30 * 3 + sum(r["weight_bytes"] for r in result["dit_rounds"]))
    # Compare each recorded op, not just the aggregate bytes: an op can span rate changes.
    for start, end, group, name, byte_count, ids in result["timeline"]:
        parts = [s for s in grouped[group, name, ids]
                 if s["start_s"] >= start and s["end_s"] <= end]
        assert parts[0]["op_fraction_start"] == pytest.approx(0)
        assert parts[-1]["op_fraction_end"] == pytest.approx(1)
        assert sum(s["dram_bytes"] for s in parts) == pytest.approx(byte_count)
        for a, b in zip(parts, parts[1:]):
            assert a["op_fraction_end"] == b["op_fraction_start"]
    vlm = [s for s in segments if s["group"] == "vlm" and s["end_s"] > s["start_s"]]
    rates = {round(s["dram_bytes"] / (s["end_s"] - s["start_s"]), 6) for s in vlm}
    assert len(rates) > 1


@pytest.mark.parametrize("period", [None, 0, -1, float("inf"), float("nan")])
def test_periodic_requires_positive_finite_period(period):
    with pytest.raises(ValueError, match="launch_period_s"):
        Simulator(HWConfig(), MapConfig(vlm_launch="periodic", launch_period_s=period))


@pytest.mark.parametrize("n", [0, -1, 1.5, True])
def test_invalid_freeze_count(n):
    with pytest.raises(ValueError, match="jit_freeze_after"):
        Simulator(HWConfig(), MapConfig(jit_freeze_after=n))
