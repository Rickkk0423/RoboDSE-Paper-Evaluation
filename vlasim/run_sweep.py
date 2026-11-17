"""Nominal hardware/mapping sweep with an example trace using the same calibration."""
import argparse
import csv
import json
from pathlib import Path
import time

from vlasim import DRAMModel, Simulator, HWConfig, MapConfig
from vlasim.dse import default_space, small_space, configured_space, validate_calibration_space, run_space, add_cost, write_csv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("calib", nargs="?", type=Path)
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--hardware", type=Path)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--n-req", type=int, default=30)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data")
    a = ap.parse_args()
    dram = DRAMModel.from_json(a.calib) if a.calib else DRAMModel()
    if a.small and a.hardware:
        ap.error("--small and --hardware are mutually exclusive")
    space = configured_space(a.hardware) if a.hardware else small_space() if a.small else default_space()
    if a.calib:
        validate_calibration_space(json.loads(a.calib.read_text()), space)
    started = time.monotonic()
    res = add_cost(run_space(space, dram=dram, procs=a.procs, n_req=a.n_req))
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"sweep_LS_{dram.version}.csv"
    write_csv(res, out)
    print(f"{len(space)} configs -> {len(res)} feasible rows in {out} ({time.monotonic()-started:.1f}s)")
    sample_hw, sample_mp = space[0]
    r = Simulator(sample_hw, sample_mp, dram=dram).run()
    with (a.out / "trace_example.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["obs_time_s", "chunk_ready_s", "L_ms"])
        w.writerows((o, d, (d-o)*1e3) for o, d in r["trace"])
    print("Area and energy use placeholder constants; do not use as calibrated cost estimates.")


if __name__ == "__main__":
    main()
