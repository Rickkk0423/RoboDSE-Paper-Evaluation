"""Compatibility wrapper for descriptive task lookup; no invented uncertainty."""
import numpy as np

try:
    from .task_report import TaskGrid
except ImportError:
    from task_report import TaskGrid


class SuccessSurface:
    def __init__(self, path, invalid_as_fail=False, total_col=360, *, allow_extrapolation=False):
        if total_col != 360:
            raise ValueError("the imported grid denominator is 360")
        self.grid = TaskGrid(path)
        self.pts = self.grid.points
        self.succ = self.grid.rates
        if invalid_as_fail:
            raise ValueError("per-speed denominators are unknown; cannot recover all-episode success")
        self.allow_extrapolation = allow_extrapolation

    @property
    def plateau(self) -> float:
        return float(self.succ.max())

    def __call__(self, L_ms, S_ms):
        """Return (descriptive mean, unknown stderr=None, outside_hull)."""
        row = self.grid.lookup(L_ms, S_ms)
        if row["status"] == "outside_measured_hull":
            if not self.allow_extrapolation:
                return float("nan"), None, True
            nearest = np.argmin(np.sum((self.pts - [L_ms, S_ms]) ** 2, axis=1))
            return float(self.succ[nearest]), None, True
        return row["valid_only"], None, False
