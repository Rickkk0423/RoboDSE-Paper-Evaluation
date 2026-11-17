"""Hardware/mapping sweep: produces L, S (and traffic / utilization / area / energy) per config.

1. enumerate hardware x mapping configurations
2. prune infeasible ones (SRAM capacity)
3. simulate each -> L and S statistics, DRAM traffic, utilization
4. attach hardware cost (area, energy) -- task success is NOT handled here (see analysis/)
"""
from __future__ import annotations
import csv
import itertools
import json
from dataclasses import asdict
from multiprocessing import Pool

from .workload import Pi05Workload, Pi05Config
from .hw import HWConfig, MapConfig
from .dram import DRAMModel
from .sim import Simulator
from .cost import CostModel


def default_space():
    hws = [HWConfig(n_cores=n, dram_bw=bw * 1e9, sram_mb=sram, local_kb=loc)
           for n, bw, sram, loc in itertools.product((1, 2, 3, 4, 6, 8),
                                                     (50, 75, 100, 150, 200, 300, 400, 800),
                                                     (8, 16, 32, 64), (512, 2048))]
    return mapping_space(hws)


def mapping_space(hws, policies=("fair", "vlm_priority", "balance")):
    def maps(hw):
        yield MapConfig(mode="serial")
        for vc, k, pol in itertools.product(range(1, hw.n_cores), (1, 2, 3),
                                            policies):
            if pol in ("vlm_priority", "dit_priority") and not hw.dram_priority:
                continue
            yield MapConfig(mode="pipelined", vlm_cores=vc, dit_stages=k, bw_policy=pol)
    return [(hw, mp) for hw in hws for mp in maps(hw)]


def configured_space(path):
    with open(path) as f:
        config = json.load(f)
    policies = config.get("policies", ["fair"])
    if not policies or set(policies) - {"fair", "balance", "vlm_priority", "dit_priority"}:
        raise ValueError("invalid bandwidth policies")
    hws = [HWConfig(**hw) for hw in config["hardware"]]
    if not hws:
        raise ValueError("hardware list must not be empty")
    return mapping_space(hws, policies)


def validate_calibration_space(calibration, space):
    metadata = calibration.get("backend_metadata", {})
    if metadata.get("backend_executed"):
        peak = metadata["peak_GBps"] * 1e9
        if any(abs(hw.dram_bw - peak) > 1 for hw, _ in space):
            raise ValueError("calibrated bandwidth is specific to backend peak; use matching --hardware")
        if not metadata.get("priority_supported", False) and any(
                mp.bw_policy in ("vlm_priority", "dit_priority") for _, mp in space):
            raise ValueError("calibrated backend does not support strict priority mappings")


def small_space():
    return [(h, m) for h, m in default_space()
            if h.n_cores <= 4 and h.dram_bw in (100e9, 200e9, 400e9)
            and h.sram_mb == 32 and h.local_kb == 2048]


def _eval(args):
    hw, mp, cfg, dram, n_req = args
    wl = Pi05Workload(cfg)
    sim = Simulator(hw, mp, wl, dram)
    if not sim.sram_ok:
        return None
    r = sim.run(n_requests=n_req, warmup=max(4, n_req // 5))
    return {**{f"hw_{k}": v for k, v in asdict(hw).items()},
            **{f"map_{k}": v for k, v in asdict(mp).items()}, **r}


def run_space(space, cfg: Pi05Config | None = None, dram: DRAMModel | None = None,
              n_req: int = 30, procs: int = 2):
    cfg, dram = cfg or Pi05Config(), dram or DRAMModel()
    jobs = [(hw, mp, cfg, dram, n_req) for hw, mp in space]
    if procs < 1:
        raise ValueError("procs must be positive")
    if procs == 1:
        return [r for job in jobs if (r := _eval(job)) is not None]
    with Pool(procs) as p:
        res = p.map(_eval, jobs, chunksize=16)
    return [r for r in res if r is not None]


def add_cost(results, cost: CostModel | None = None, wl: Pi05Workload | None = None):
    cost, wl = cost or CostModel(), wl or Pi05Workload()
    FV, _ = wl.vlm_totals(); FD, _ = wl.dit_totals_per_request()
    for r in results:
        hw = HWConfig(**{k[3:]: v for k, v in r.items() if k.startswith("hw_")})
        r.update(cost_status="placeholder_not_calibrated", area_mm2=cost.area(hw),
                 energy_J=cost.energy_per_req(hw, FV + FD, r["dram_GB_per_req"] * 1e9, r["S_mean"]))
    return results


def write_csv(results, path):
    if not results:
        raise ValueError("no feasible configurations to write")
    keys = [k for k in results[0].keys() if k not in ("trace", "timeline")]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(results)
