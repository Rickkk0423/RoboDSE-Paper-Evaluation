"""Check unpaced, previously unfitted tile sizes and stream ratios against DRAM capacity."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import seq_stream, interleave
from vlasim import DRAMModel


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("output exists; choose a new directory")
    args.out.mkdir(parents=True)
    cal = json.loads(args.calib.read_text())
    if json.loads(args.config.read_text()) != cal["backend_metadata"]["config"]:
        raise ValueError("validation DRAM configuration differs from calibration")
    total = 4 * 2**20
    seq = args.out / "heldout_seq_256KB.csv"
    with seq.open("w") as f:
        for offset in range(0, total, 256 * 1024):
            seq_stream(f, "vlm", 256 * 1024, base=offset * 2)
    traces = [(seq, 1)]
    for ratio in (0.4, 0.6):
        path = args.out / f"heldout_mix_{int(ratio*100)}.csv"
        with path.open("w") as f:
            first_bytes = int(total / 64 * ratio) * 64
            interleave(f, "vlm", "dit", first_bytes, total - first_bytes)
        traces.append((path, 2))
    native = args.out / "native"
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_native.py")),
                    *[str(p) for p, _ in traces], "--backend", str(args.backend),
                    "--config", str(args.config), "--out", str(native)], check=True)
    peak = cal["backend_metadata"]["peak_GBps"]
    dram = DRAMModel.from_json(args.calib)
    corners = [DRAMModel(**dict(zip(cal["ranges"], point)))
               for point in itertools.product(*cal["ranges"].values())]
    results = []
    for path, active in traces:
        measured = json.loads((native / f"{path.stem}.json").read_text())
        actual = measured["achieved_GBps"]
        predicted = dram.effective_bw(peak, active)
        lower = min(d.effective_bw(peak, active) for d in corners)
        upper = max(d.effective_bw(peak, active) for d in corners)
        error = (predicted / actual - 1) * 100
        results.append({"case": path.stem, "measured_GBps": actual,
                        "predicted_GBps": predicted, "nominal_error_pct": error,
                        "within_10pct": abs(error) <= 10,
                        "interval_GBps": [lower, upper], "inside_interval": lower <= actual <= upper,
                        "native": measured})
    root = Path(__file__).resolve().parents[2]
    source_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted((root / "vlasim").rglob("*.py"))}
    report = {"calibration": cal, "cases": results, "source_hashes": source_hashes,
              "nominal_gate": "pass" if all(r["within_10pct"] for r in results) else "failed",
              "interval_gate": "pass" if all(r["inside_interval"] for r in results) else "failed",
              "scope": "Independent saturated address microbenchmarks not used in fit; does not validate VLA compute or end-to-end inference."}
    (args.out / "capacity_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("nominal_gate", "interval_gate")}, indent=2))


if __name__ == "__main__":
    main()
