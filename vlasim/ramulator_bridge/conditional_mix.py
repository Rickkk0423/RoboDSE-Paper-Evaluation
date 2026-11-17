"""Experimental ratio-conditioned lookup for explicitly supported address phases."""
import math
from statistics import median


def experiment_cases():
    """Freeze split membership before native results exist."""
    cases = []
    for shift in (0, 512, 4096, 65536):
        for ratio in (25, 50, 75):
            for size in (1, 4, 16):
                cases.append(dict(shift_bytes=shift, ratio_pct=ratio, size_mib=size,
                                  split="train" if size in (1, 4) else "heldout_size"))
        for ratio in (40, 60):
            for size in (4, 16):
                cases.append(dict(shift_bytes=shift, ratio_pct=ratio, size_mib=size,
                                  split="heldout_ratio"))
    for ratio in (25, 40, 50, 60, 75):
        for size in (4, 16):
            cases.append(dict(shift_bytes=64, ratio_pct=ratio, size_mib=size,
                              split="unsupported_layout"))
    for case in cases:
        case["case"] = (f"mix{case['ratio_pct']}_shift{case['shift_bytes']}"
                        f"_size{case['size_mib']}MiB")
    return cases


def fit_conditions(rows):
    """Use only predeclared training rows; never fit a held-out result."""
    groups = {}
    for row in rows:
        if row["split"] != "train":
            continue
        value = row["measured_GBps"]
        if not math.isfinite(value) or value <= 0:
            raise ValueError("training bandwidth must be finite and positive")
        key = (row["shift_bytes"], row["ratio_pct"])
        groups.setdefault(key, []).append(value)
    if not groups:
        raise ValueError("no training rows")
    return [{"shift_bytes": shift, "ratio_pct": ratio, "GBps": median(values),
             "training_count": len(values)}
            for (shift, ratio), values in sorted(groups.items())]


def predict(conditions, shift_bytes, ratio_pct):
    """Interpolate ratio only, never interpolate or extrapolate address layout."""
    points = sorted((p["ratio_pct"], p["GBps"]) for p in conditions
                    if p["shift_bytes"] == shift_bytes)
    if not points:
        return None, "unsupported_layout"
    if not math.isfinite(ratio_pct) or not points[0][0] <= ratio_pct <= points[-1][0]:
        return None, "unsupported_ratio"
    for ratio, value in points:
        if ratio == ratio_pct:
            return value, "supported"
    for (a, x), (b, y) in zip(points, points[1:]):
        if a < ratio_pct < b:
            return x + (y - x) * (ratio_pct - a) / (b - a), "supported"
    raise ValueError("invalid conditional table")


def evaluate(rows, conditions, baseline):
    results = []
    for row in rows:
        value, status = predict(conditions, row["shift_bytes"], row["ratio_pct"])
        actual = row["measured_GBps"]
        if not math.isfinite(actual) or actual <= 0:
            raise ValueError("measurement must be finite and positive")
        error = None if value is None else (value / actual - 1) * 100
        results.append(dict(row, predicted_GBps=value, prediction_status=status,
                            error_pct=error, within_10pct=None if error is None else abs(error) <= 10,
                            scalar_error_pct=(baseline / actual - 1) * 100))
    groups = {}
    for split in sorted({r["split"] for r in results}):
        subset = [r for r in results if r["split"] == split]
        errors = [abs(r["error_pct"]) for r in subset if r["error_pct"] is not None]
        groups[split] = {"cases": len(subset), "predicted": len(errors),
                         "abstained": len(subset) - len(errors),
                         "max_abs_error_pct": max(errors) if errors else None,
                         "mean_abs_error_pct": sum(errors) / len(errors) if errors else None,
                         "scalar_mean_abs_error_pct": sum(abs(r["scalar_error_pct"]) for r in subset) / len(subset),
                         "gate": ("abstained" if not errors else
                                  "pass" if len(errors) == len(subset) and max(errors) <= 10 else "failed")}
    return results, groups
