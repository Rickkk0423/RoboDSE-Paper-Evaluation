"""Recheck all shortlisted candidates at every DRAM sample with longer runs."""
import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

from robustness import parameter_points
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator


def scalar(value):
    if value == "":
        return None
    if value in ("True", "False"):
        return value == "True"
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shortlist", type=Path)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cal = json.loads(args.calib.read_text())
    with args.shortlist.open(newline="") as f:
        rows = list(csv.DictReader(f))
    results = []
    for row in rows:
        hw = HWConfig(**{k[3:]: scalar(v) for k, v in row.items() if k.startswith("hw_")})
        mp = MapConfig(**{k[4:]: scalar(v) for k, v in row.items() if k.startswith("map_")})
        for point in parameter_points(cal, 3):
            params = dict(zip(("eta_seq", "eta_mix", "prio_leak"), point))
            samples = []
            for n in (30, 120):
                r = Simulator(hw, mp, dram=DRAMModel(**params)).run(n_requests=n, warmup=max(6, n // 5))
                samples.append(dict(requests=n, L_ms=r["L_mean"] * 1e3, S_ms=r["S_mean"] * 1e3))
            results.append(dict(hardware=asdict(hw), mapping=asdict(mp), params=params, samples=samples,
                                L_delta_pct=(samples[1]["L_ms"] / samples[0]["L_ms"] - 1) * 100,
                                S_delta_pct=(samples[1]["S_ms"] / samples[0]["S_ms"] - 1) * 100))
    report = dict(cases=results, max_abs_L_delta_pct=max(abs(r["L_delta_pct"]) for r in results),
                  max_abs_S_delta_pct=max(abs(r["S_delta_pct"]) for r in results),
                  scope="Deterministic shortlisted mappings at all 33 sampled v2 points; no continuous/stochastic validation")
    (args.out / "convergence_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
