"""Reproduce compute rows and add matched k=1/k=2 round diagnostics."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def summarize(result):
    rounds = result["dit_rounds"]
    start, end = result["measurement_window_s"]
    steady = [r for r in rounds if r["start_s"] >= start - 1e-12
              and r["end_s"] <= end + 1e-12]
    busy = sum(max(0.0, min(end, r["end_s"]) - max(start, r["start_s"])) for r in rounds)
    fields = ("duration_s", "compute_s", "exposed_memory_s", "linear_s", "attention_s", "wait_before_s")
    return dict(
        dit_busy=result["dit_busy"], vlm_busy=result["vlm_busy"],
        busy_scope="whole run including fill/drain; occupied wall time, not PE utilization",
        dit_steady_busy=busy / (end - start),
        steady_window_s=[start, end], steady_round_count=len(steady),
        steady_round_mean_ms={k.removesuffix("_s"): sum(r[k] for r in steady) / len(steady) * 1000
                              for k in fields},
        steady_round_mean_GB=sum(r["dram_bytes"] for r in steady) / len(steady) / 1e9,
        steady_round_mean_weight_GB=sum(r["weight_bytes"] for r in steady) / len(steady) / 1e9,
        steady_round_mean_active_requests=sum(sum(x is not None for x in r["stage_request_ids"])
                                            for r in steady) / len(steady),
        time_accounting="duration=compute+exposed_memory=linear+attention; compute/DRAM overlap via roofline max, not additive raw memory service; wait_before is outside round",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline = json.loads(args.baseline.read_text())
    if json.loads(args.calib.read_text()) != baseline["calibration"]:
        raise ValueError("calibration differs from baseline")
    manifest_hash = hashlib.sha256((args.snapshot / "source_manifest.json").read_bytes()).hexdigest()
    if manifest_hash != baseline["compute_snapshot_sha256"]:
        raise ValueError("snapshot differs from baseline")
    args.out.mkdir(parents=True, exist_ok=False)
    wl = Pi05Workload()
    provider = NeuSimTiming(args.snapshot, wl, allow_analytical_siglip=True)
    configs = [(row, False) for row in baseline["hybrid_results"]]
    configs += [(dict(row, stages=1, mapping=dict(row["mapping"], dit_stages=1)), True)
                for row in baseline["hybrid_results"] if row["mode"] == "pipelined" and row["stages"] == 2]
    rows = []
    for row, control in configs:
        hw, mp = HWConfig(**row["hardware"]), MapConfig(**row["mapping"])
        result = Simulator(hw, mp, wl=wl, dram=DRAMModel.from_json(args.calib),
                           compute_time_fn=provider).run(n_requests=row["requests"],
                                                       warmup=max(6, row["requests"] // 5), diagnostics=True)
        if not control:
            for key in ("L", "S"):
                if abs(result[key + "_mean"] * 1000 - row[key + "_ms"]) > 1e-8:
                    raise ValueError("baseline timing did not reproduce")
        rows.append(dict(cores=hw.n_cores, mode=mp.mode, stages=mp.dit_stages,
                         requests=row["requests"], matched_k1_control=control,
                         hardware=asdict(hw), mapping=asdict(mp),
                         vlm_group_cores=hw.n_cores if mp.mode == "serial" else mp.vlm_cores,
                         dit_group_cores=hw.n_cores if mp.mode == "serial" else hw.n_cores - mp.vlm_cores,
                         L_ms=result["L_mean"] * 1000, S_ms=result["S_mean"] * 1000,
                         dit_GB_per_req=result["dit_GB_per_req"],
                         dram_GB_per_req=result["dram_GB_per_req"], sram_ok=result["sram_ok"],
                         kv_on_chip=result["kv_on_chip"], act_on_chip=result["act_on_chip"],
                         **summarize(result), dit_rounds=result["dit_rounds"]))
    report = dict(baseline_report=str(args.baseline),
                  baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                  compute_snapshot_sha256=manifest_hash, calibration=baseline["calibration"],
                  source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                 (Path(__file__), Path(__file__).parent / "vlasim/sim.py",
                                  Path(__file__).parent / "vlasim/neusim_compute.py",
                                  Path(__file__).parent / "vlasim/kernel_shapes.py",
                                  Path(__file__).parent / "vlasim/workload.py")},
                  neuSim_shape_evaluations=sum(m.calls for m in provider.models.values()),
                  resolved_op_calls=provider.resolved_calls, analytical_siglip_calls=provider.fallback_calls,
                  hybrid_results=rows,
                  scope="Same estimated-shape unsliced hybrid as baseline; serial k=1 uses all cores, matched pipeline k=1/k=2 preserve group allocation. Whole-run bytes include fill/drain; steady round bytes count shared weights once, not per participant.")
    (args.out / "compute_report.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in rows:
        if row["requests"] == 120:
            print(json.dumps({k: v for k, v in row.items() if k not in ("dit_rounds", "hardware", "mapping")}))


if __name__ == "__main__":
    main()
