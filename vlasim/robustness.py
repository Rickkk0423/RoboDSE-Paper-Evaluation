"""Sweep a DRAM interval and select mappings on finite sampled parameter points."""
import argparse
import csv
from dataclasses import asdict
import itertools
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from vlasim import DRAMModel
from vlasim.dse import default_space, small_space, configured_space, validate_calibration_space, run_space, write_csv

ROOT = Path(__file__).resolve().parent
PARAMS = ("eta_seq", "eta_mix", "prio_leak")
TIE_RTOL = 1e-6


def identity(row, prefix):
    return tuple((k, row[k]) for k in sorted(row) if k.startswith(prefix))


def parameter_points(cal, count):
    if count < 2:
        raise ValueError("--points must be at least 2 to cover interval endpoints")
    DRAMModel(**cal["params"])
    axes = []
    for k in PARAMS:
        lo, hi = cal["ranges"][k]
        if not lo <= cal["params"][k] <= hi:
            raise ValueError(f"nominal {k} must lie inside its range")
        for value in (lo, hi):
            DRAMModel(**{**cal["params"], k: value})
        axes.append(np.linspace(lo, hi, count).tolist() if lo != hi else [lo])
    points = set(itertools.product(*axes))
    nominal = tuple(cal["params"][k] for k in PARAMS)
    points.add(nominal)
    # Evaluate sensitivity at exact nominal axes, not their nearest grid neighbors.
    for i, axis in enumerate(axes):
        for endpoint in (axis[0], axis[-1]):
            point = list(nominal)
            point[i] = endpoint
            points.add(tuple(point))
    return sorted(points)


def summarize(rows, budget_ms):
    by_cfg, by_hw = {}, {}
    point_count = len({tuple(r[k] for k in PARAMS) for r in rows})
    for r in rows:
        by_cfg.setdefault(identity(r, ("hw_", "map_")), []).append(r)
        by_hw.setdefault(identity(r, "hw_"), {}).setdefault(
            tuple(r[k] for k in PARAMS), []).append(r)
    summaries = []
    for cfg, samples in by_cfg.items():
        ls = [r["L_mean"] * 1e3 for r in samples]
        ss = [r["S_mean"] * 1e3 for r in samples]
        summaries.append({**dict(cfg), "L_min_ms": min(ls), "L_max_ms": max(ls),
                          "S_min_ms": min(ss), "S_max_ms": max(ss),
                          "S_spread_pct": (max(ss) - min(ss)) / np.mean(ss) * 100,
                          "sampled_points": len(samples),
                          "feasible_all_points": bool(len(samples) == point_count and max(ls) <= budget_ms)})
    decisions, shortlist = [], []
    for hw, points in by_hw.items():
        picks = []
        for samples in points.values():
            feasible = [r for r in samples if r["L_mean"] * 1e3 <= budget_ms]
            best_s = min(r["S_mean"] for r in feasible) if feasible else None
            picks.append({identity(r, "map_") for r in feasible
                          if r["S_mean"] <= best_s * (1 + TIE_RTOL)})
        common = set.intersection(*picks)
        if not any(picks):
            status = "infeasible_all_points"
        elif not all(picks):
            status = "feasibility_changes"
        elif common:
            status = "stable_on_sampled_points"
        else:
            status = "mapping_changes"
        candidates = [r for r in summaries if identity(r, "hw_") == hw
                      and r["feasible_all_points"]]
        best = min(candidates, key=lambda r: r["S_max_ms"]) if candidates else None
        decisions.append({"hardware": dict(hw), "status": status,
                          "sampled_points": len(points),
                          "distinct_feasible_winners": len(set.union(*picks)),
                          "common_optimal_mappings": [dict(p) for p in sorted(common, key=str)],
                          "robust_candidate": best})
        if best:
            shortlist.append(best)
    return summaries, decisions, sorted(shortlist, key=lambda r: r["S_max_ms"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--points", type=int, default=3)
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--hardware", type=Path, help="explicit hardware/policy search space JSON")
    ap.add_argument("--L_max_ms", type=float, default=250.0)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--n-req", type=int, default=30)
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument("--from-csv", type=Path, help="reanalyze saved robust_LS.csv without rerunning simulation")
    a = ap.parse_args(argv)
    if a.L_max_ms <= 0:
        ap.error("latency budget must be positive")
    cal = json.loads(a.calib.read_text())
    points = parameter_points(cal, a.points)
    if a.small and a.hardware:
        ap.error("--small and --hardware are mutually exclusive")
    space = configured_space(a.hardware) if a.hardware else small_space() if a.small else default_space()
    validate_calibration_space(cal, space)
    print(f"{len(space)} configs x {len(points)} DRAM points ({cal['version']})", flush=True)
    started, rows = time.monotonic(), []
    if a.from_csv:
        def scalar(value):
            if value in ("True", "False"):
                return value == "True"
            if value == "":
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        with a.from_csv.open(newline="") as f:
            rows = [{k: scalar(v) for k, v in r.items()} for r in csv.DictReader(f)]
        if {tuple(r[k] for k in PARAMS) for r in rows} != set(points):
            raise ValueError("saved DRAM sample points do not match requested calibration/grid")
        if any(r["dram_version"] != cal["version"] for r in rows):
            raise ValueError("saved calibration version does not match")
        expected = {(tuple(sorted(asdict(h).items())), tuple(sorted(asdict(m).items()))) for h, m in space}
        actual = {(tuple((k[3:], v) for k, v in identity(r, "hw_")),
                   tuple((k[4:], v) for k, v in identity(r, "map_"))) for r in rows}
        if not actual <= expected:
            raise ValueError("saved configurations are outside requested space")
        if len(rows) != len(actual) * len(points):
            raise ValueError("saved sweep is incomplete")
        observations = {(identity(r, ("hw_", "map_")), tuple(r[k] for k in PARAMS)) for r in rows}
        if len(observations) != len(rows):
            raise ValueError("saved sweep has duplicate config/parameter rows")
    for index, point in enumerate([] if a.from_csv else points, 1):
        params = dict(zip(PARAMS, point))
        batch = run_space(space, dram=DRAMModel(**params, version=cal["version"]),
                          procs=a.procs, n_req=a.n_req)
        for row in batch:
            row.pop("trace", None)
            row.update(params)
            row["n_requests"] = a.n_req
        rows.extend(batch)
        print(f"  point {index}/{len(points)}: {len(batch)} feasible configs", flush=True)
    summaries, decisions, shortlist = summarize(rows, a.L_max_ms)
    if not rows:
        raise ValueError("no feasible hardware/mapping configurations")
    sensitivity = {}
    nominal = cal["params"]
    for key in PARAMS:
        means = []
        for endpoint in cal["ranges"][key]:
            samples = [r["S_mean"] for r in rows if all(
                r[k] == (endpoint if k == key else nominal[k]) for k in PARAMS)]
            means.append(float(np.mean(samples)) * 1e3)
        sensitivity[key] = means[1] - means[0]
    counts = {status: sum(d["status"] == status for d in decisions)
              for status in sorted({d["status"] for d in decisions})}
    report = {"calibration": cal, "latency_budget_ms": a.L_max_ms,
              "scope": "configured" if a.hardware else "small" if a.small else "full",
              "hardware_space": json.loads(a.hardware.read_text()) if a.hardware else None,
              "mapping_tie_relative_tolerance": TIE_RTOL,
              "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "n_requests": rows[0].get("n_requests") if a.from_csv else a.n_req,
              "source_rows": str(a.from_csv.resolve()) if a.from_csv else None,
              "parameter_points": len(points), "configurations": len(summaries),
              "rows": len(rows), "decision_counts": counts,
              "S_spread_median_pct": float(np.median([r["S_spread_pct"] for r in summaries])),
              "S_spread_p90_pct": float(np.percentile([r["S_spread_pct"] for r in summaries], 90)),
              "sensitivity_mean_S_delta_ms": sensitivity, "decisions": decisions,
              "limitations": ["Finite sampled points, not proof over a continuous interval.",
                              "Workload structure and compute utilization are estimates.",
                              "DRAM calibration is limited to the backend configuration and issue policy recorded in its metadata.",
                              "Compute remains analytical, not NeuSim-calibrated."]}
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, a.out / "robust_LS.csv")
    write_csv(summaries, a.out / "robust_summary.csv")
    if shortlist:
        write_csv(shortlist, a.out / "shortlist.csv")
    else:
        (a.out / "shortlist.csv").write_text("S_max_ms\n")
    (a.out / "decision_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"decisions": counts, "sensitivity_ms": sensitivity,
                      "shortlist": len(shortlist), "elapsed_s": round(time.monotonic() - started, 1)}, indent=2))


if __name__ == "__main__":
    main()
