"""Dense near-balance and fixed-global-ratio controls; no model is fitted."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import interleave, REGION
from stream_patterns import uniform_order, skew_order, shuffled_order, describe_order, experiment_cases


def make_trace(path, case):
    total = case["size_mib"] * 2**20 // 64
    a_count = total * case["ratio_bp"] // 10000
    bases = (REGION["vlm"], REGION["dit"] + case["shift_bytes"])
    if case["pattern"] == "legacy":
        with path.open("w") as f:
            interleave(f, "vlm", "dit", a_count * 64, (total - a_count) * 64, bases=bases)
        with path.open(newline="") as f:
            descriptor = describe_order(0 if row[1] == "vlm" else 1 for row in csv.reader(f))
    else:
        if case["pattern"] == "uniform":
            order = uniform_order(a_count, total - a_count)
        elif case["pattern"] == "skew":
            order = skew_order(total, case["parameter"])
        elif case["pattern"] == "shuffle":
            order = shuffled_order(total, case["parameter"])
        else:
            raise ValueError("unknown stream pattern")
        def emit(f):
            cursors = [0, 0]
            for stream in order:
                address = bases[stream] + cursors[stream] * 64
                f.write(f"0,{('vlm', 'dit')[stream]},R,{address:#x}\n")
                cursors[stream] += 1
                yield stream
        with path.open("w") as f:
            descriptor = describe_order(emit(f))
    if descriptor["stream_requests"] != [a_count, total - a_count]:
        raise ValueError("generated stream counts differ from predeclared traffic")
    return descriptor


def main():
    import yaml
    from analyze_layout import summarize_channels

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cal = json.loads(args.calib.read_text())
    if json.loads(args.config.read_text()) != cal["backend_metadata"]["config"]:
        raise ValueError("configuration differs from pinned calibration")
    args.out.mkdir(parents=True, exist_ok=False)
    cases = experiment_cases()
    source = Path(__file__).resolve().parent
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
              for name in ("probe_balance.py", "stream_patterns.py", "gen_traces.py", "run_native.py", "analyze_layout.py")}
    manifest = {"cases": cases, "source_hashes": hashes, "baseline_calibration": cal,
                "scope": "Prospective diagnostic sweep, not a model fit or independent VLA validation. All-read saturated FIFO, same pinned backend.",
                "hypotheses": ["Near-balanced capacity may depend on traffic size and cumulative stream progress.",
                               "Identical global ratio and per-stream addresses need not determine capacity.",
                               "Integer-count and legacy float schedules need a generator control."]}
    manifest_path = args.out / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    traces = args.out / "traces"
    traces.mkdir()
    descriptors = {case["case"]: make_trace(traces / (case["case"] + ".csv"), case) for case in cases}
    (args.out / "offered_descriptors.json").write_text(json.dumps(descriptors, indent=2) + "\n")
    native = args.out / "native"
    subprocess.run([sys.executable, str(source / "run_native.py"),
                    *[str(traces / (c["case"] + ".csv")) for c in cases],
                    "--backend", str(args.backend), "--config", str(args.config),
                    "--out", str(native)], check=True)
    rows = []
    for case in cases:
        measured = json.loads((native / (case["case"] + ".json")).read_text())
        stats_path = native / (case["case"] + "_stats.yaml")
        counters = summarize_channels(yaml.safe_load(stats_path.read_text()))
        desc = descriptors[case["case"]]
        if (measured["completed"] != measured["accepted"] or measured["completed"] != desc["requests"] * 2
                or counters["num_read_reqs"] != measured["completed"]
                or [measured["stream_transactions"][str(i)] for i in (0, 1)] != [n * 2 for n in desc["stream_requests"]]):
            raise ValueError("native transaction accounting differs from offered trace")
        rows.append(dict(case, native=measured, offered=desc, counters=counters,
                         stats_sha256=hashlib.sha256(stats_path.read_bytes()).hexdigest()))
    controls = []
    for row in rows:
        if row["pattern"] == "legacy":
            exact = next(r for r in rows if r["pattern"] == "uniform" and r["size_mib"] == row["size_mib"]
                         and r["ratio_bp"] == row["ratio_bp"] and r["shift_bytes"] == row["shift_bytes"])
            controls.append({"legacy_case": row["case"], "integer_case": exact["case"],
                             "trace_identical": row["native"]["trace_sha256"] == exact["native"]["trace_sha256"],
                             "bandwidth_delta_pct": (row["native"]["achieved_GBps"] / exact["native"]["achieved_GBps"] - 1) * 100})
    contrasts = {}
    for shift in (0, 4096):
        subset = [r for r in rows if r["ratio_bp"] == 5000 and r["size_mib"] == 4
                  and r["shift_bytes"] == shift and r["pattern"] != "legacy"]
        values = {r["case"]: r["native"]["achieved_GBps"] for r in subset}
        contrasts[str(shift)] = {"GBps": values, "max_min_ratio": max(values.values()) / min(values.values())}
    report = {"cases": rows, "generator_controls": controls, "fixed_ratio_contrasts": contrasts,
              "source_hashes": hashes, "experiment_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "offered_descriptors_sha256": hashlib.sha256((args.out / "offered_descriptors.json").read_bytes()).hexdigest(),
              "native_metadata": json.loads((native / "metadata.json").read_text()),
              "scope": manifest["scope"], "dse_integration": "none; no predictive model fitted"}
    (args.out / "balance_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"generator_controls": controls, "fixed_ratio_contrasts": contrasts}, indent=2))


if __name__ == "__main__":
    main()
