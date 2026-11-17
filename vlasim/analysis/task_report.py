"""Descriptive task-grid lookup of candidates, with explicit coverage abstention."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import ConvexHull


class TaskGrid:
    def __init__(self, path):
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            if not fields or len(fields) != 7:
                raise ValueError("expected L/S, valid-count, three speeds and reported mean")
            rows = list(reader)
        points, rates, valid = [], [], []
        for row in rows:
            values = [float(row[n]) for n in fields]
            l, s, n, *percentages = values
            if (not np.isfinite(values).all() or min(l, s) < 0 or not n.is_integer()
                    or not 0 < n <= 360 or any(not 0 <= p <= 100 for p in percentages)):
                raise ValueError("invalid task-grid row")
            points.append((l, s)); valid.append(n)
            rates.append(percentages[-1] / 100)
        if len(set(points)) != len(points) or len(points) < 3:
            raise ValueError("duplicate or insufficient task-grid points")
        self.points = np.array(points)
        self.rates = np.array(rates)
        self.valid = np.array(valid)
        self.valid_interpolator = LinearNDInterpolator(self.points, self.rates)
        self.all_interpolator = LinearNDInterpolator(self.points, self.rates * self.valid / 360)
        self.hull = ConvexHull(self.points)

    def lookup(self, l_ms, s_ms):
        if not np.isfinite([l_ms, s_ms]).all():
            raise ValueError("query must be finite")
        valid = float(np.asarray(self.valid_interpolator(l_ms, s_ms)).item())
        boundary_adjusted = False
        if np.isnan(valid):
            point = np.array([l_ms, s_ms])
            violations = self.hull.equations[:, :2] @ point + self.hull.equations[:, 2]
            if violations.max() <= 1e-8:
                direction = self.points.mean(axis=0) - point
                point += direction / np.linalg.norm(direction) * 1e-8
                l_ms, s_ms = map(float, point)
                valid = float(np.asarray(self.valid_interpolator(l_ms, s_ms)).item())
                boundary_adjusted = True
        if np.isnan(valid):
            return dict(status="outside_measured_hull", valid_only=None, coverage_weighted_proxy=None)
        return dict(status="interpolated", valid_only=valid,
                    boundary_adjusted=boundary_adjusted,
                    coverage_weighted_proxy=float(np.asarray(self.all_interpolator(l_ms, s_ms)).item()))


def candidate_ranges(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def identity(row):
    def scalar(value):
        if value in ("", "None"):
            return None
        if value in ("True", "False"):
            return value == "True"
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return tuple((k, scalar(row[k])) for k in sorted(row) if k.startswith(("hw_", "map_")))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("grid", type=Path)
    ap.add_argument("shortlist", type=Path)
    ap.add_argument("--samples", type=Path, help="raw robust CSV to preserve correlated L/S pairs")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    grid = TaskGrid(args.grid)
    sampled = candidate_ranges(args.samples) if args.samples else []
    candidates = []
    for index, row in enumerate(candidate_ranges(args.shortlist)):
        corners = [dict(L_ms=float(row[l]), S_ms=float(row[s]),
                        **grid.lookup(float(row[l]), float(row[s])))
                   for l in ("L_min_ms", "L_max_ms") for s in ("S_min_ms", "S_max_ms")]
        samples = [dict(L_ms=float(r["L_mean"]) * 1000, S_ms=float(r["S_mean"]) * 1000,
                        **grid.lookup(float(r["L_mean"]) * 1000, float(r["S_mean"]) * 1000))
                   for r in sampled if identity(r) == identity(row)]
        if args.samples and len(samples) != int(row["sampled_points"]):
            raise ValueError("candidate sample set incomplete or duplicated")
        supported = [s for s in samples if s["status"] == "interpolated"]
        candidates.append(dict(index=index, cores=int(row["hw_n_cores"]), mode=row["map_mode"], corners=corners,
                               samples=samples, supported_sample_count=len(supported), total_sample_count=len(samples),
                               reported_mean_range=[min(s["valid_only"] for s in supported), max(s["valid_only"] for s in supported)] if supported else None,
                               coverage="all_samples_in_hull" if samples and len(samples) == len(supported) else "partial_or_outside",
                               scope="Correlated sampled L/S pairs when supplied; bounding corners are diagnostic only. No continuous task bound."))
    report = dict(grid_sha256=hashlib.sha256(args.grid.read_bytes()).hexdigest(),
                  shortlist_sha256=hashlib.sha256(args.shortlist.read_bytes()).hexdigest(),
                  samples_sha256=hashlib.sha256(args.samples.read_bytes()).hexdigest() if args.samples else None,
                  boundary_roundoff_tolerance_ms=1e-8,
                  grid_points=len(grid.points), grid_L_range_ms=[float(grid.points[:, 0].min()), float(grid.points[:, 0].max())],
                  grid_S_range_ms=[float(grid.points[:, 1].min()), float(grid.points[:, 1].max())],
                  candidates=candidates, ranking_gate="blocked_unverified_task_transfer_and_cost",
                  limitations=["Imported task results have no verified checkpoint/environment provenance in this repository.",
                               "Mean success is an average over speeds; per-speed episode denominators are unknown, so no binomial SE is claimed.",
                               "Multiplying reported mean by valid/360 is a coverage-weighted sensitivity proxy, not recovered all-episode success.",
                               "Hardware L/S means need not reproduce task-side delay semantics or delay distributions.",
                               "No nearest-neighbor extrapolation, final hardware ranking or cost/energy Pareto claim."])
    (args.out / "task_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("grid_points", "grid_L_range_ms", "grid_S_range_ms", "ranking_gate")}, indent=2))


if __name__ == "__main__":
    main()
