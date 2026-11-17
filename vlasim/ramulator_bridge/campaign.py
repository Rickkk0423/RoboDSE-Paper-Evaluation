"""Run a bounded native calibration, matched DSE and held-out paced-replay campaign."""
import argparse
import csv
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from fit_dram import fit
from gen_traces import micro, segment
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def run(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--sizes", type=float, nargs="+", default=[1, 4, 16])
    ap.add_argument("--config", type=Path, default=ROOT / "configs/hbm2_8ch.json")
    ap.add_argument("--space", type=Path, default=ROOT / "configs/dse_hbm2_8ch.json")
    args = ap.parse_args()
    if args.out.exists():
        ap.error("campaign output exists; select a fresh directory")
    args.out.mkdir(parents=True)
    rows, sessions = [], []
    trace_names = ([f"seq_{kb}KB.csv" for kb in (4, 64, 1024)]
                   + [f"mix_{r}.csv" for r in (25, 50, 75)] + ["rw_10.csv", "rw_30.csv"])
    for size in args.sizes:
        traces = args.out / f"micro_{size:g}mb"
        traces.mkdir()
        micro(traces, size)
        output = args.out / f"native_{size:g}mb"
        run(HERE / "run_native.py", *[traces / name for name in trace_names],
            "--backend", args.backend, "--config", args.config, "--out", output)
        with (output / "measurements.csv").open(newline="") as f:
            rows.extend(csv.DictReader(f))
        sessions.append({"size_mib": size, "directory": str(output),
                         "metadata": json.loads((output / "metadata.json").read_text())})
    measurements = args.out / "measurements.csv"
    with measurements.open("w", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    previous = json.loads((ROOT / "vlasim/calib/dram_v0_prior.json").read_text())
    calibrated = fit(rows, previous)
    calibrated["backend_metadata"] = {**sessions[0]["metadata"], "sessions": sessions}
    calibrated["source_results"] = str(measurements.resolve())
    calibrated["note"] = ("HBM2 eight-channel native calibration; eta_mix is a relative factor that "
                          "may exceed one due to address locality. Physical bandwidth is capped at peak. "
                          "RW diagnostics do not calibrate a write penalty; strict priority remains unmeasured.")
    calib = args.out / "dram_v1_hbm2_8ch.json"
    calib.write_text(json.dumps(calibrated, indent=2) + "\n")
    nominal, robust, candidates = (args.out / name for name in ("nominal", "robust", "candidates"))
    run(HERE.parent / "run_sweep.py", calib, "--hardware", args.space,
        "--procs", args.procs, "--out", nominal)
    run(HERE.parent / "robustness.py", calib, "--hardware", args.space, "--points", 3,
        "--procs", args.procs, "--out", robust)
    run(HERE.parent / "check_candidates.py", robust / "shortlist.csv", calib, "--out", candidates)
    configs = sorted(candidates.glob("candidate_*.json"))[:3]
    validation = []
    for path in configs:
        cfg = json.loads(path.read_text())
        hw, mp = HWConfig(**cfg["hardware"]), MapConfig(**cfg["mapping"])
        dram = DRAMModel.from_json(calib)
        sim = Simulator(hw, mp, dram=dram).run(n_requests=30)
        t0_ms = sim["trace"][len(sim["trace"]) // 2][0] * 1e3
        trace_dir = args.out / "heldout" / path.stem
        trace_dir.mkdir(parents=True)
        segment(trace_dir, t0_ms, 0.02, hw, mp, dram)
        trace = next(trace_dir.glob("segment_*.csv"))
        native = trace_dir / "native"
        run(HERE / "run_native.py", trace, "--backend", args.backend,
            "--config", args.config, "--out", native)
        measured = json.loads((native / f"{trace.stem}.json").read_text())
        error = (measured["completion_time_ns"] / 20_000 - 1) * 100
        validation.append({"candidate": path.name, "config": cfg,
                           "model_window_ns": 20_000, "native": measured,
                           "timing_error_pct": error, "within_10pct": abs(error) <= 10})
    decisions = json.loads((robust / "decision_report.json").read_text())
    report = {"host": platform.node(), "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
              "python": sys.version, "calibration": calibrated,
              "evaluated_rows": decisions["rows"], "decision_counts": decisions["decision_counts"],
              "validation": validation,
              "validation_gate": "pass_for_paced_replay_only" if validation and all(v["within_10pct"] for v in validation) else "failed",
              "limitations": ["Native simulator measurements, not silicon measurements.",
                              "Global FIFO injection with backpressure is part of calibration scope.",
                              "Finite grids and padded empirical intervals are not statistical guarantees.",
                              "Held-out segments are model-paced, uniform per op, all reads; not independent end-to-end validation.",
                              "Compute, area, energy, and task success remain uncalibrated."]}
    (args.out / "campaign_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"params": calibrated["params"], "ranges": calibrated["ranges"],
                      "decisions": decisions["decision_counts"], "validation_gate": report["validation_gate"],
                      "validation_errors_pct": [v["timing_error_pct"] for v in validation]}, indent=2))


if __name__ == "__main__":
    main()
