"""Hold byte ratio fixed and change stream address phase under the pinned backend."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import interleave, REGION


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("output exists; select a fresh directory")
    args.out.mkdir(parents=True)
    paths = []
    for shift in (0, 64, 512, 4096, 65536):
        path = args.out / f"phase50_shift_{shift}.csv"
        with path.open("w") as f:
            interleave(f, "vlm", "dit", 2 * 2**20, 2 * 2**20,
                       bases=(REGION["vlm"], REGION["dit"] + shift))
        paths.append(path)
    output = args.out / "native"
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_native.py")),
                    *map(str, paths), "--backend", str(args.backend), "--config", str(args.config),
                    "--out", str(output)], check=True)
    rows = [json.loads((output / f"{p.stem}.json").read_text()) for p in paths]
    report = {"scope": "Fixed balanced byte mix; only DiT address base changes; global FIFO issue policy.",
              "cases": rows, "bandwidth_ratio_max_min": max(r["achieved_GBps"] for r in rows) / min(r["achieved_GBps"] for r in rows)}
    (args.out / "aliasing_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"GBps": {r["benchmark"]: r["achieved_GBps"] for r in rows},
                      "max_min_ratio": report["bandwidth_ratio_max_min"]}, indent=2))


if __name__ == "__main__":
    main()
