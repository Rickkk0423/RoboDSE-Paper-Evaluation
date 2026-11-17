"""Frozen trace-level ridge baseline using offered state, not native outcomes."""
import csv
import math

import numpy as np

EDGES = [-65536, -16384, -4096, -1024, 0, 1024, 4096, 16384, 65536]
FEATURES = [f"signed_bin_{i}" for i in range(10)] + [
    "switch_fraction", "log_max_run", "log_mean_run", "log_requests", "signed_ratio",
    "log_mean_abs_progress", "negative_fraction"]


def features_from_order(order):
    streams = np.fromiter(order, dtype=np.int8)
    if not len(streams) or not np.isin(streams, [0, 1]).all():
        raise ValueError("expected nonempty stream 0/1 order")
    signed = np.cumsum(np.where(streams == 0, 1, -1), dtype=np.int64) * 64
    histogram = np.bincount(np.searchsorted(EDGES, signed, side="right"), minlength=10) / len(streams)
    changes = np.flatnonzero(np.diff(streams)) + 1
    runs = np.diff(np.r_[0, changes, len(streams)])
    return [*map(float, histogram), len(changes) / max(len(streams) - 1, 1),
            math.log1p(int(runs.max())), math.log(len(streams) / len(runs)),
            math.log(len(streams)), float(np.mean(streams == 0) * 2 - 1),
            math.log1p(float(np.mean(np.abs(signed)))), float(np.mean(signed < 0))]


def features_from_trace(path):
    with path.open(newline="") as f:
        def labels():
            for row in csv.reader(f):
                if len(row) != 4 or row[0] != "0" or row[1] not in ("vlm", "dit") or row[2] != "R":
                    raise ValueError("model supports saturated two-stream read traces only")
                yield 0 if row[1] == "vlm" else 1
        return features_from_order(labels())


def fit_model(rows, peak=256.0, alpha=1.0):
    training = [r for r in rows if r["split"] == "train"]
    if not training or not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("training data and positive regularization required")
    models = []
    for shift in sorted({r["shift_bytes"] for r in training}):
        subset = [r for r in training if r["shift_bytes"] == shift]
        if any(not math.isfinite(r["GBps"]) or not 0 < r["GBps"] <= peak for r in subset):
            raise ValueError("invalid training bandwidth")
        x = np.array([r["features"] for r in subset], dtype=float)
        if x.ndim != 2 or x.shape[1] != len(FEATURES) or not np.isfinite(x).all():
            raise ValueError("invalid features")
        center, scale = x.mean(axis=0), x.std(axis=0)
        scale[scale < 1e-12] = 1
        z = (x - center) / scale
        y = np.log([r["GBps"] for r in subset])
        offset = y.mean()
        coefficients = np.linalg.solve(z.T @ z + alpha * np.eye(x.shape[1]), z.T @ (y - offset))
        models.append(dict(shift_bytes=shift, center=center.tolist(), scale=scale.tolist(),
                           coefficients=coefficients.tolist(), intercept=float(offset),
                           train_count=len(subset), scalar_GBps=float(np.exp(offset))))
    return dict(version="experimental-offered-state-ridge-v1", features=FEATURES,
                alpha=alpha, peak_GBps=peak, models=models,
                scope="Trace-level saturated-read makespan bandwidth; not a runtime DSE resource model")


def predict(model, shift, features):
    condition = next((m for m in model["models"] if m["shift_bytes"] == shift), None)
    if condition is None:
        return None, "unsupported_layout"
    x = np.asarray(features, dtype=float)
    if x.shape != (len(FEATURES),) or not np.isfinite(x).all():
        raise ValueError("invalid features")
    z = (x - condition["center"]) / condition["scale"]
    log_value = condition["intercept"] + z @ condition["coefficients"]
    value = float(np.exp(np.clip(log_value, 0, math.log(model["peak_GBps"]))))
    return value, "supported"


def heldout_cases():
    cases = []
    for shift in (0, 4096):
        for ratio in (4850, 4980, 4995, 5005, 5020, 5150):
            cases.append(dict(shift_bytes=shift, ratio_bp=ratio, size_mib=8,
                              pattern="uniform", parameter=0, split="new_ratio"))
        for ratio in (4995, 5000, 5005):
            cases.append(dict(shift_bytes=shift, ratio_bp=ratio, size_mib=2,
                              pattern="uniform", parameter=0, split="new_size"))
        for pattern, parameters in (("skew", (4, 64)), ("shuffle", (41, 73)), ("blocked", (8, 128))):
            for parameter in parameters:
                cases.append(dict(shift_bytes=shift, ratio_bp=5000, size_mib=8,
                                  pattern=pattern, parameter=parameter, split="new_" + pattern))
    for pattern, ratio, parameter in (("uniform", 4995, 0), ("uniform", 5000, 0),
                                      ("uniform", 5005, 0), ("shuffle", 5000, 41)):
        cases.append(dict(shift_bytes=512, ratio_bp=ratio, size_mib=8,
                          pattern=pattern, parameter=parameter, split="unsupported_layout"))
    for case in cases:
        case["case"] = (f"{case['pattern']}{case['parameter']}_bp{case['ratio_bp']}"
                        f"_shift{case['shift_bytes']}_{case['size_mib']}MiB")
    return cases
