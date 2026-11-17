"""Run a predeclared conditional mixed-bandwidth experiment, separate from DSE."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from conditional_mix import experiment_cases, fit_conditions, evaluate
from gen_traces import interleave, REGION


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cal = json.loads(args.calib.read_text())
    if json.loads(args.config.read_text()) != cal["backend_metadata"]["config"]:
        raise ValueError("backend configuration differs from baseline")
    args.out.mkdir(parents=True, exist_ok=False)
    cases = experiment_cases()
    manifest = {"cases": cases, "fit": "median sizes 1/4 MiB at ratios 25/50/75 per supported phase",
                "predict": "linear ratio interpolation, no layout interpolation or extrapolation",
                "gate_abs_error_pct": 10, "baseline_calibration": cal,
                "scope": "All-read saturated sequential stream pairs, fixed FIFO/controller; not VLA validation."}
    manifest_path = args.out / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    traces = args.out / "traces"
    traces.mkdir()
    for case in cases:
        total = case["size_mib"] * 2**20
        a_bytes = int(total // 64 * case["ratio_pct"] / 100) * 64
        with (traces / (case["case"] + ".csv")).open("w") as f:
            interleave(f, "vlm", "dit", a_bytes, total - a_bytes,
                       bases=(REGION["vlm"], REGION["dit"] + case["shift_bytes"]))
    native = args.out / "native"
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_native.py")),
                    *[str(traces / (c["case"] + ".csv")) for c in cases],
                    "--backend", str(args.backend), "--config", str(args.config),
                    "--out", str(native)], check=True)
    rows = []
    for case in cases:
        measured = json.loads((native / (case["case"] + ".json")).read_text())
        rows.append(dict(case, measured_GBps=measured["achieved_GBps"], native=measured))
    conditions = fit_conditions(rows)
    baseline = cal["backend_metadata"]["peak_GBps"] * cal["params"]["eta_seq"] * cal["params"]["eta_mix"]
    results, groups = evaluate(rows, conditions, baseline)
    source = Path(__file__).resolve().parent
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
              for name in ("conditional_mix.py", "layout_campaign.py", "gen_traces.py", "run_native.py")}
    report = {"experiment_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "source_hashes": hashes, "native_metadata": json.loads((native / "metadata.json").read_text()),
              "conditions": conditions, "groups": groups, "cases": results,
              "dse_integration": "not integrated; model lacks workload layout inputs and independent VLA validation",
              "scope": manifest["scope"]}
    (args.out / "layout_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
