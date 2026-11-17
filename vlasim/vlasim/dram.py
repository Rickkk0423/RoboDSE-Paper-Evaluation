"""Analytical (fluid, rate-based) DRAM layer.

Bandwidth is shared among concurrently active streams. Parameters are meant to be
CALIBRATED against Ramulator2 micro-benchmarks (single sequential stream efficiency,
two-stream interleaving loss, priority behaviour). Defaults below are placeholders.
"""
import json
import math
from dataclasses import dataclass, asdict


@dataclass
class DRAMModel:
    eta_seq: float = 0.85      # efficiency of a single large sequential stream (refresh, turnarounds)
    eta_mix: float = 0.92      # relative mixed-stream factor; locality/parallelism may make it >1
    prio_leak: float = 0.0     # fraction of high-priority demand still disturbed by low-priority traffic
    version: str = "placeholder"

    def __post_init__(self):
        if not 0 < self.eta_seq <= 1:
            raise ValueError("eta_seq must be in (0, 1]")
        if not math.isfinite(self.eta_mix) or self.eta_mix <= 0:
            raise ValueError("eta_mix must be finite and positive")
        if not 0 <= self.prio_leak < 1:
            raise ValueError("prio_leak must be in [0, 1)")

    # ---- versioned parameter files (calib/*.json) ----
    @classmethod
    def from_json(cls, path: str) -> "DRAMModel":
        d = json.load(open(path))
        p = d.get("params", d)
        return cls(**{k: p[k] for k in ("eta_seq", "eta_mix", "prio_leak") if k in p},
                   version=d.get("version", path))

    def to_json(self, path: str, **meta):
        json.dump({"version": self.version, "params": {k: v for k, v in asdict(self).items()
                                                        if k != "version"}, **meta},
                  open(path, "w"), indent=2)

    def effective_bw(self, peak: float, n_active: int) -> float:
        bw = peak * self.eta_seq
        if n_active >= 2:
            bw *= self.eta_mix
        return min(peak, bw)

    def balance_targets(self, peak: float, remaining: dict[str, tuple[float, float]]) -> dict[str, float]:
        """Progress-aware split. remaining[s] = (compute_time_left, bytes_left) of the stream's
        current unit of work (VLM: rest of this request; DiT: rest of this round).
        Choose per-stream bandwidth so all units are predicted to finish together, i.e. the slower
        stage gets more bandwidth:  T* = max(max_i C_i, sum_i B_i / BW),  b_i = B_i / T*."""
        live = {k: v for k, v in remaining.items() if v[1] > 0}
        if not live:
            return {k: 0.0 for k in remaining}
        bw = self.effective_bw(peak, len(live))
        T = max(max(c for c, _ in live.values()), sum(b for _, b in live.values()) / bw)
        return {k: (remaining[k][1] / T if k in live else 0.0) for k in remaining}

    def allocate(self, peak: float, demands: dict[str, float], policy: str,
                 targets: dict[str, float] | None = None) -> dict[str, float]:
        if policy == "balance" and targets is not None:
            # give each stream up to its progress-aware target, then hand leftovers out fairly
            bw = self.effective_bw(peak, sum(1 for d in demands.values() if d > 0))
            alloc = {k: min(demands[k], targets.get(k, 0.0)) for k in demands}
            rem = bw - sum(alloc.values())
            hungry = {k: demands[k] - alloc[k] for k in demands if demands[k] - alloc[k] > 1e-9}
            while rem > 1e-9 and hungry:
                share = rem / len(hungry)
                for k in list(hungry):
                    g = min(share, hungry[k]); alloc[k] += g; rem -= g; hungry[k] -= g
                    if hungry[k] <= 1e-9:
                        del hungry[k]
            return alloc
        return self._allocate_static(peak, demands, policy)

    def _allocate_static(self, peak: float, demands: dict[str, float], policy: str) -> dict[str, float]:
        """demands: stream -> desired bytes/s (rate needed to run compute-limited).
        Returns allocated bytes/s per stream (water-filling)."""
        active = {k: d for k, d in demands.items() if d > 0}
        if not active:
            return {k: 0.0 for k in demands}
        bw = self.effective_bw(peak, len(active))
        alloc = {k: 0.0 for k in demands}
        if policy in ("dit_priority", "vlm_priority") and len(active) >= 2:
            hi = "dit" if policy == "dit_priority" else "vlm"
            order = [hi] + [k for k in active if k != hi]
            rem = bw
            for i, k in enumerate(order):
                if k not in active:
                    continue
                a = min(active[k], rem)
                if i == 0:              # high-priority stream still loses prio_leak to interference
                    a *= (1.0 - self.prio_leak)
                alloc[k] = a
                rem -= a
            return alloc
        # max-min fair water-filling
        rem, left = bw, dict(active)
        while left:
            share = rem / len(left)
            sat = {k: d for k, d in left.items() if d <= share}
            if not sat:
                for k in left:
                    alloc[k] = share
                break
            for k, d in sat.items():
                alloc[k] = d
                rem -= d
                del left[k]
        return alloc
