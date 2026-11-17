"""Check nominal request-count convergence and export robust candidates for replay."""
import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

from vlasim import DRAMModel, HWConfig, MapConfig, Simulator


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shortlist", type=Path)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--long-requests", type=int, default=120)
    args = ap.parse_args()
    dram = DRAMModel.from_json(args.calib)
    with args.shortlist.open(newline="") as f:
        rows = list(csv.DictReader(f))
    args.out.mkdir(parents=True, exist_ok=True)
    reports = []
    for index, row in enumerate(rows):
        # CSV values follow the dataclass scalar types, including JSON-like nulls.
        def parse(value):
            if value == "True":
                return True
            if value == "False":
                return False
            if value == "":
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        hw = HWConfig(**{k[3:]: parse(v) for k, v in row.items() if k.startswith("hw_")})
        mp = MapConfig(**{k[4:]: parse(v) for k, v in row.items() if k.startswith("map_")})
        config = {"hardware": asdict(hw), "mapping": asdict(mp)}
        path = args.out / f"candidate_{index:02d}.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        values = []
        for n in (30, args.long_requests):
            result = Simulator(hw, mp, dram=dram).run(n_requests=n, warmup=max(4, n // 5))
            values.append({"requests": n, "L_ms": result["L_mean"] * 1e3,
                           "S_ms": result["S_mean"] * 1e3})
        reports.append({"config": path.name, "samples": values,
                        "L_delta_pct": (values[1]["L_ms"] / values[0]["L_ms"] - 1) * 100,
                        "S_delta_pct": (values[1]["S_ms"] / values[0]["S_ms"] - 1) * 100})
    report = {"calibration": json.loads(args.calib.read_text()),
              "scope": "Nominal-point convergence only, not interval-wide validation.",
              "candidates": reports}
    (args.out / "convergence.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
