"""Freeze a state-feature model before running prospective native holdouts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import REGION, blocked_balanced
from probe_balance import make_trace
from state_model import FEATURES, features_from_trace, fit_model, predict, heldout_cases


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--training", type=Path, required=True)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    training_report = args.training / "balance_report.json"
    prior = json.loads(training_report.read_text())
    if json.loads(args.config.read_text()) != prior["native_metadata"]["config"]:
        raise ValueError("configuration differs from training")
    cases = heldout_cases()
    source = Path(__file__).resolve().parent
    names = ("state_model.py", "state_campaign.py", "stream_patterns.py", "probe_balance.py", "gen_traces.py", "run_native.py")
    manifest = {"cases": cases, "features": FEATURES, "alpha": 1.0, "target": "makespan_GBps",
                "training_report_sha256": digest(training_report),
                "source_hashes": {n: digest(source / n) for n in names},
                "gate": "every supported held-out case absolute bandwidth error <= 10%; abstention is not a pass",
                "no_tuning": "Use all 42 non-legacy Phase 4 cases; no held-out outcomes are available at fit time."}
    manifest_path = args.out / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    training = []
    for row in prior["cases"]:
        if row["pattern"] == "legacy":
            continue
        trace = args.training / "traces" / (row["case"] + ".csv")
        if digest(trace) != row["native"]["trace_sha256"]:
            raise ValueError("training trace hash mismatch")
        training.append(dict(case=row["case"], split="train", shift_bytes=row["shift_bytes"],
                             GBps=row["native"]["makespan_GBps"], features=features_from_trace(trace)))
    if len(training) != 42 or len({r["case"] for r in training}) != 42:
        raise ValueError("unexpected training set")
    model = fit_model(training)
    model_path = args.out / "frozen_model.json"
    model_path.write_text(json.dumps(model, indent=2) + "\n")
    (args.out / "training_features.json").write_text(json.dumps(training, indent=2) + "\n")
    traces = args.out / "traces"
    traces.mkdir()
    predictions = []
    for case in cases:
        path = traces / (case["case"] + ".csv")
        if case["pattern"] == "blocked":
            with path.open("w") as f:
                blocked_balanced(f, case["size_mib"] * 2**19, case["parameter"], case["shift_bytes"])
        else:
            make_trace(path, case)
        features = features_from_trace(path)
        value, status = predict(model, case["shift_bytes"], features)
        predictions.append(dict(case, features=features, predicted_GBps=value,
                                status=status, trace_sha256=digest(path)))
    predictions_path = args.out / "frozen_predictions.json"
    predictions_path.write_text(json.dumps(predictions, indent=2) + "\n")
    frozen_hash = digest(predictions_path)
    native = args.out / "native"
    subprocess.run([sys.executable, str(source / "run_native.py"),
                    *[str(traces / (c["case"] + ".csv")) for c in cases], "--backend", str(args.backend),
                    "--config", str(args.config), "--out", str(native)], check=True)
    metadata = json.loads((native / "metadata.json").read_text())
    for key in ("source_manifest_sha256", "library_sha256", "memory_library_sha256", "expanded_config_sha256",
                "issue_width_transactions_per_cycle", "max_outstanding_transactions"):
        if metadata[key] != prior["native_metadata"][key]:
            raise ValueError("backend changed since training: " + key)
    if digest(predictions_path) != frozen_hash:
        raise ValueError("frozen predictions changed")
    results = []
    for row in predictions:
        measured = json.loads((native / (row["case"] + ".json")).read_text())
        if measured["trace_sha256"] != row["trace_sha256"] or measured["accepted"] != measured["completed"]:
            raise ValueError("native trace/accounting mismatch")
        actual = measured["makespan_GBps"]
        condition = next((m for m in model["models"] if m["shift_bytes"] == row["shift_bytes"]), None)
        error = None if row["predicted_GBps"] is None else (row["predicted_GBps"] / actual - 1) * 100
        baseline = None if condition is None else (condition["scalar_GBps"] / actual - 1) * 100
        results.append(dict(row, native=measured, error_pct=error, baseline_error_pct=baseline))
    groups = {}
    for split in sorted({r["split"] for r in results}):
        subset = [r for r in results if r["split"] == split]
        errors = [abs(r["error_pct"]) for r in subset if r["error_pct"] is not None]
        groups[split] = dict(cases=len(subset), predicted=len(errors),
                             max_abs_error_pct=max(errors) if errors else None,
                             mean_abs_error_pct=sum(errors) / len(errors) if errors else None,
                             gate="abstained" if not errors else "pass" if len(errors) == len(subset) and max(errors) <= 10 else "failed")
    report = dict(manifest_sha256=digest(manifest_path), frozen_model_sha256=digest(model_path),
                  frozen_predictions_sha256=frozen_hash, cases=results, groups=groups, native_metadata=metadata,
                  scope="Prospective trace-level prediction only; no DSE integration or VLA validation")
    (args.out / "state_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
