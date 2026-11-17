"""Fit DRAMModel parameters from Ramulator2 micro-benchmark results and write calib/dram_vN.json.

Input CSV (one row per Ramulator run you have finished so far; partial sets are fine):
  benchmark,peak_GBps,achieved_GBps[,hi_achieved_GBps,hi_demand_GBps]
  e.g.  seq_1024KB,204.8,176.3
        mix_50,204.8,161.0
        prio_50,204.8,160.2,95.1,102.4
Parameters without measurements keep the previous file's interval, so each finished batch of
Ramulator runs narrows the interval robustness.py sweeps -- DSE never waits for the full set.

usage: python3 ramulator_bridge/fit_dram.py results.csv calib/dram_v0_prior.json calib/dram_v1.json
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import re
import numpy as np


def fraction(row, numerator, denominator):
    num, den = float(row[numerator]), float(row[denominator])
    if not math.isfinite(num) or not math.isfinite(den) or den <= 0 or not 0 <= num <= den:
        raise ValueError(f"invalid measured ratio for {row['benchmark']}: {numerator}/{denominator}")
    return num / den


def fit(rows, previous, pad=0.02):
    if not 0 < pad < 1:
        raise ValueError("pad must be in (0, 1)")
    out = copy.deepcopy(previous)
    params, ranges = out["params"], out["ranges"]
    seq, mix, balanced_mix, pri = [], [], [], []
    for row in rows:
        kind = row["benchmark"].split("_")[0]
        if kind == "seq":
            seq.append(fraction(row, "achieved_GBps", "peak_GBps"))
        elif kind == "mix":
            value = fraction(row, "achieved_GBps", "peak_GBps")
            mix.append(value)
            if re.match(r"mix_50(?:$|_)", row["benchmark"]):
                balanced_mix.append(value)
        elif kind == "prio" and row.get("hi_achieved_GBps"):
            pri.append(1 - fraction(row, "hi_achieved_GBps", "hi_demand_GBps"))
    if not (seq or mix or pri):
        raise ValueError("no supported calibration measurements")

    def setp(key, values):
        if not values:
            return
        low = 0.0 if key == "prio_leak" else 1e-6
        high = 1 - 1e-6 if key == "prio_leak" else float("inf") if key == "eta_mix" else 1.0
        if any(not low <= v <= high for v in values):
            raise ValueError(f"measurements cannot be represented by {key}; check model or measurement setup")
        params[key] = float(np.median(values))
        ranges[key] = [max(low, min(values) - pad), min(high, max(values) + pad)]

    setp("eta_seq", seq)
    if mix:
        setp("eta_mix", [m / params["eta_seq"] for m in mix])
        if balanced_mix:
            params["eta_mix"] = float(np.median(balanced_mix)) / params["eta_seq"]
        # Propagate single-stream uncertainty through the multiplicative model.
        lo, hi = ranges["eta_seq"]
        ranges["eta_mix"] = [max(1e-6, min(mix) / hi - pad), max(mix) / lo + pad]
    setp("prio_leak", pri)
    match = re.match(r"v(\d+)", previous.get("version", "v0"))
    if not match:
        raise ValueError("previous calibration version must start with v<number>")
    out.update(version=f"v{int(match.group(1)) + 1}-ramulator",
               measured={"seq": len(seq), "mix": len(mix), "prio": len(pri)},
               mix_nominal_reference="balanced mix_50 for saturated fair sharing" if balanced_mix else "median available mixes; balanced reference unavailable",
               fit_note="Empirical range with padding, not a statistical confidence interval; may expand if measurements contradict prior.")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("previous", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--metadata", type=Path, help="JSON with backend revision, DRAM org, address mapping and controller")
    ap.add_argument("--pad", type=float, default=0.02)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output already exists; write a new version instead")
    with args.results.open(newline="") as f:
        rows = list(csv.DictReader(f))
    out = fit(rows, json.loads(args.previous.read_text()), args.pad)
    if args.metadata:
        out["backend_metadata"] = json.loads(args.metadata.read_text())
    out["source_results"] = str(args.results.resolve())
    out["previous_calibration"] = str(args.previous.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
