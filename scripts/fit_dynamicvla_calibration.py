"""Fit an independent DynamicVLA DRAM calibration JSON from native results."""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit(measurements, trace_manifest, profile, output):
    rows = list(csv.DictReader(measurements.open(newline="")))
    seq = [float(r["achieved_GBps"]) / float(r["peak_GBps"])
           for r in rows if r["benchmark"].startswith("seq_dynamicvla_")]
    mix = [float(r["achieved_GBps"]) / float(r["peak_GBps"])
           for r in rows if r["benchmark"].startswith("mix_dynamicvla_")]
    if not seq:
        raise ValueError("native measurements contain no DynamicVLA sequence rows")
    eta_seq = statistics.median(seq)
    eta_mix = statistics.median(mix) / eta_seq if mix else None
    result = {
        "schema": 1,
        "model": "dynamicvla",
        "status": "complete" if mix else "partial_sequence_only",
        "params": {"eta_seq": eta_seq, "eta_mix": eta_mix, "prio_leak": None},
        "ranges": {
            "eta_seq": [min(seq), max(seq)],
            "eta_mix": ([min(mix) / max(seq), max(mix) / min(seq)] if mix else None),
            "prio_leak": None,
        },
        "source": {
            "measurements_sha256": sha256(measurements),
            "trace_manifest_sha256": sha256(trace_manifest),
            "profile_sha256": sha256(profile),
        },
        "fit_method": "median achieved/peak ratios; empirical min/max envelope",
        "rows": rows,
        "limitations": [
            "Native Ramulator measurements are simulator evidence, not silicon measurements.",
            "The fit is valid only for the recorded DynamicVLA traffic and controller scope.",
            "Priority behavior is unmeasured and intentionally null.",
            "This calibration must not be substituted into Pi0.5 results.",
        ],
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("measurements", type=Path)
    ap.add_argument("trace_manifest", type=Path)
    ap.add_argument("profile", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output exists; write a new calibration version")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(fit(args.measurements, args.trace_manifest, args.profile, args.output), indent=2))


if __name__ == "__main__":
    main()
