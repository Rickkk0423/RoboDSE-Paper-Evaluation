import copy
import importlib.util
import io
import json
from pathlib import Path

import pytest
import numpy as np

from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.dse import default_space, run_space, small_space, write_csv
from vlasim.workload import Op

ROOT = Path(__file__).resolve().parents[1]


def load_script(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


robust = load_script("robustness", "vlasim/robustness.py")
calibration = load_script("fit_dram", "vlasim/ramulator_bridge/fit_dram.py")
traces = load_script("gen_traces", "vlasim/ramulator_bridge/gen_traces.py")


@pytest.fixture
def prior():
    return json.loads((ROOT / "vlasim/calib/dram_v0_prior.json").read_text())


def test_spaces():
    assert len(default_space()) == 10752
    assert len(small_space()) == 174


@pytest.mark.parametrize("params", [{"eta_seq": 0}, {"eta_mix": -1},
                                    {"prio_leak": 1}, {"eta_seq": float("nan")}])
def test_invalid_dram(params):
    with pytest.raises(ValueError):
        DRAMModel(**params)


@pytest.mark.parametrize("policy", ["fair", "vlm_priority", "dit_priority", "balance"])
def test_bandwidth_conservation(policy):
    dram = DRAMModel()
    alloc = dram.allocate(100, {"vlm": 200, "dit": 200}, policy,
                          dram.balance_targets(100, {"vlm": (1, 100), "dit": (2, 100)}))
    assert all(v >= 0 for v in alloc.values())
    assert sum(alloc.values()) <= dram.effective_bw(100, 2) + 1e-9


def test_simulator_repeatable():
    sim = Simulator(HWConfig(), MapConfig())
    first = sim.run(n_requests=16, warmup=4)
    second = sim.run(n_requests=16, warmup=4)
    assert first == second


def test_too_few_requests():
    with pytest.raises(ValueError, match="steady-state"):
        Simulator(HWConfig(), MapConfig()).run(n_requests=10)


def test_balance_uses_compute_hook():
    sim = Simulator(HWConfig(), MapConfig(bw_policy="balance"),
                    compute_time_fn=lambda op, group, peak, hw: 7)
    sim.g["vlm"].cur = Op("current", 1, 1, 10, "vlm")
    sim.g["vlm"].rem = 0.5
    sim.g["vlm"].ops.append(Op("next", 1, 1, 20, "vlm"))
    assert sim._remaining()["vlm"] == (10.5, 25)


def test_nondivisible_batched_round_records_actual_participants():
    sim = Simulator(HWConfig(), MapConfig(dit_stages=3))
    ops = list(sim._dit_round_ops([10, 20, 30]))
    assert ops[0].request_ids == (10, 20, 30)
    assert ops[-1].request_ids == (10,)
    sim = Simulator(HWConfig(), MapConfig(dit_stages=3, dit_batching=False))
    assert all(len(op.request_ids) == 1 for op in sim._dit_round_ops([10, 20, 30]))


def test_single_process_and_pruning():
    rows = run_space([(HWConfig(n_cores=1), MapConfig(mode="serial")),
                      (HWConfig(n_cores=1, local_kb=1), MapConfig(mode="serial"))],
                     n_req=12, procs=1)
    assert len(rows) == 1
    assert rows[0]["S_mean"] == pytest.approx(rows[0]["L_mean"])


def test_csv_excludes_nested_timeline(tmp_path):
    target = tmp_path / "rows.csv"
    write_csv([{"L": 1, "trace": [], "timeline": []}], target)
    assert target.read_text().splitlines() == ["L", "1"]
    with pytest.raises(ValueError):
        write_csv([], target)


def test_points_cover_nominal_corners_and_exact_axes(prior):
    points = robust.parameter_points(prior, 3)
    nominal = tuple(prior["params"][k] for k in robust.PARAMS)
    assert nominal in points
    assert (0.7, 0.8, 0.0) in points
    assert (0.95, 1.0, 0.2) in points
    assert (0.7, nominal[1], nominal[2]) in points
    assert len(points) == len(set(points))
    with pytest.raises(ValueError):
        robust.parameter_points(prior, 1)


def sample_rows(latencies, maps=None):
    rows = []
    for i, latency in enumerate(latencies):
        rows.append({"hw_n_cores": 4, "map_mode": "pipelined",
                     "map_vlm_launch": maps[i] if maps else "jit",
                     "eta_seq": 0.7 + i * 0.1, "eta_mix": 0.9, "prio_leak": 0,
                     "L_mean": latency / 1000, "S_mean": 0.05})
    return rows


@pytest.mark.parametrize("latencies,status", [([200, 220], "stable_on_sampled_points"),
                                               ([300, 320], "infeasible_all_points"),
                                               ([200, 320], "feasibility_changes")])
def test_decision_status(latencies, status):
    _, decisions, shortlist = robust.summarize(sample_rows(latencies), 250)
    assert decisions[0]["status"] == status
    assert bool(shortlist) == (status == "stable_on_sampled_points")


def test_full_mapping_identity_matters():
    rows = sample_rows([200, 220], ["jit", "eager"])
    _, decisions, shortlist = robust.summarize(rows, 250)
    assert decisions[0]["status"] == "mapping_changes"
    assert shortlist == []


def test_report_serializes_numpy_statistics():
    rows = sample_rows([200, 220])
    for row in rows:
        row["L_mean"] = np.float64(row["L_mean"])
        row["S_mean"] = np.float64(row["S_mean"])
    json.dumps(robust.summarize(rows, 250))


def test_numerical_ties_do_not_create_mapping_instability():
    rows = sample_rows([200, 220])
    extra = copy.deepcopy(rows)
    for r in extra:
        r["map_vlm_launch"] = "eager"
    rows[0]["S_mean"] += 1e-9
    extra[1]["S_mean"] += 1e-9
    decisions = robust.summarize(rows + extra, 250)[1]
    assert decisions[0]["status"] == "stable_on_sampled_points"
    assert len(decisions[0]["common_optimal_mappings"]) == 2


def test_partial_calibration_preserves_unmeasured_and_metadata(prior):
    prior["backend_metadata"] = {"revision": "fixture"}
    saved = copy.deepcopy(prior)
    out = calibration.fit([{"benchmark": "seq_1024KB", "peak_GBps": "100", "achieved_GBps": "80"}], prior)
    assert out["version"] == "v1-ramulator"
    assert out["params"]["eta_seq"] == 0.8
    assert out["ranges"]["eta_mix"] == prior["ranges"]["eta_mix"]
    assert out["backend_metadata"] == {"revision": "fixture"}
    assert prior == saved


def test_mix_uncertainty_propagates(prior):
    out = calibration.fit([{"benchmark": "mix_50", "peak_GBps": "100", "achieved_GBps": "75"}], prior)
    assert out["ranges"]["eta_mix"][0] == pytest.approx(0.75 / 0.95 - 0.02)
    assert out["ranges"]["eta_mix"][1] == pytest.approx(0.75 / 0.70 + 0.02)


def test_mixed_locality_gain_does_not_exceed_physical_peak(prior):
    out = calibration.fit([
        {"benchmark": "seq_4KB", "peak_GBps": "100", "achieved_GBps": "50"},
        {"benchmark": "mix_25", "peak_GBps": "100", "achieved_GBps": "60"}], prior)
    assert out["params"]["eta_mix"] == pytest.approx(1.2)
    assert DRAMModel(eta_seq=0.9, eta_mix=1.5).effective_bw(100, 2) == 100


def test_fair_nominal_uses_balanced_mix_but_interval_keeps_other_ratios(prior):
    rows = [{"benchmark": name, "peak_GBps": "100", "achieved_GBps": achieved}
            for name, achieved in [("seq_4KB", "50"), ("mix_25", "60"),
                                   ("mix_50", "30"), ("mix_75", "55")]]
    result = calibration.fit(rows, prior)
    assert result["params"]["eta_mix"] == pytest.approx(0.6)
    assert result["ranges"]["eta_mix"][1] > 1.2


@pytest.mark.parametrize("achieved", ["nan", "-1", "101", "0"])
def test_bad_calibration_rejected(prior, achieved):
    with pytest.raises(ValueError):
        calibration.fit([{"benchmark": "seq_4KB", "peak_GBps": "100", "achieved_GBps": achieved}], prior)


def test_trace_byte_counts_and_write_fraction(tmp_path):
    traces.micro(tmp_path, total_mb=0.0625)
    for path in tmp_path.glob("*.csv"):
        lines = path.read_text().splitlines()
        assert len(lines) == 1024
        if path.stem == "rw_30":
            assert sum(",W," in line for line in lines) == int(1024 * 0.3)


def test_interleave_ratio():
    output = io.StringIO()
    traces.interleave(output, "vlm", "dit", 64 * 3, 64 * 9)
    lines = output.getvalue().splitlines()
    assert len(lines) == 12
    assert sum(",vlm," in line for line in lines) == 3


def test_fresh_report_and_saved_rows_reanalysis(tmp_path, prior, monkeypatch):
    for key in robust.PARAMS:
        prior["ranges"][key] = [prior["params"][key]] * 2
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps(prior))
    monkeypatch.setattr(robust, "small_space", lambda: [
        (HWConfig(n_cores=1, local_kb=2048), MapConfig(mode="serial"))])
    out = tmp_path / "results"
    args = [str(cal), "--small", "--points", "2", "--n-req", "12",
            "--procs", "1", "--out", str(out)]
    robust.main(args)
    fresh = json.loads((out / "decision_report.json").read_text())
    assert fresh["n_requests"] == 12
    assert fresh["rows"] == 1
    robust.main(args + ["--from-csv", str(out / "robust_LS.csv")])
    restored = json.loads((out / "decision_report.json").read_text())
    assert restored["n_requests"] == 12
    assert restored["decisions"] == fresh["decisions"]
