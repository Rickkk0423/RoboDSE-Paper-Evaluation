"""Vary offered stream burst order without changing ratio, addresses or backend."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import blocked_balanced


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = [dict(shift_bytes=shift, burst_lines=burst, case=f"shift{shift}_burst{burst}")
             for shift in (0, 4096) for burst in (1, 2, 4, 8, 16, 64)]
    manifest = {"cases": cases, "per_stream_bytes": 2 * 2**20,
                "scope": "Fixed 50:50 all-read byte mix and per-stream addresses; only offered interleave order changes. Native FIFO policy unchanged."}
    manifest_path = args.out / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    paths = []
    for case in cases:
        path = args.out / (case["case"] + ".csv")
        with path.open("w") as f:
            blocked_balanced(f, manifest["per_stream_bytes"], case["burst_lines"], case["shift_bytes"])
        paths.append(path)
    native = args.out / "native"
    subprocess.run([sys.executable, str(Path(__file__).with_name("run_native.py")),
                    *map(str, paths), "--backend", str(args.backend), "--config", str(args.config),
                    "--out", str(native)], check=True)
    rows = [dict(case, native=json.loads((native / (case["case"] + ".json")).read_text())) for case in cases]
    groups = {}
    for shift in (0, 4096):
        subset = [r for r in rows if r["shift_bytes"] == shift]
        values = {str(r["burst_lines"]): r["native"]["achieved_GBps"] for r in subset}
        groups[str(shift)] = {"GBps_by_burst_lines": values, "max_min_ratio": max(values.values()) / min(values.values())}
    source = Path(__file__).resolve().parent
    report = {"cases": rows, "groups": groups, "scope": manifest["scope"],
              "native_metadata": json.loads((native / "metadata.json").read_text()),
              "experiment_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "source_hashes": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                for name in ("probe_issue_order.py", "gen_traces.py", "run_native.py")}}
    (args.out / "issue_order_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
