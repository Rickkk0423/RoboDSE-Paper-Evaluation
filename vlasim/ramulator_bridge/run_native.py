"""Execute timed 64-byte CSV traces through the isolated native Ramulator bridge."""
import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np


def load_backend(root):
    global _native_dependency
    source = root / "source"
    # Calibration uses single-thread, cycle-stepped semantics, not experimental accelerators.
    for key in list(os.environ):
        if key.startswith("NR_"):
            del os.environ[key]
    os.environ["RAMULATOR_ROOT"] = str(source / "third_party/ramulator2/python")
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    # The copied integration's Linux RPATH assumes its original directory layout.
    _native_dependency = ctypes.CDLL(str(source / "third_party/ramulator2" / f"libramulator{suffix}"),
                                     mode=ctypes.RTLD_GLOBAL)
    sys.path.insert(0, str(source))
    from neusim_ramulator.dram import Ramulator, export_config
    return Ramulator, export_config


def requests(path, tx_bytes, capacity):
    if tx_bytes <= 0 or 64 % tx_bytes:
        raise ValueError("backend transaction size must divide the 64-byte trace line")
    previous = -1.0
    with path.open(newline="") as f:
        for index, row in enumerate(csv.reader(f), 1):
            if len(row) != 4:
                raise ValueError(f"{path}:{index}: expected time,stream,R/W,address")
            issue = float(row[0])
            if not math.isfinite(issue) or issue < previous or issue < 0:
                raise ValueError(f"{path}:{index}: issue timestamps must be finite, nonnegative and sorted")
            previous = issue
            if row[1] not in ("vlm", "dit", "kv", "act"):
                raise ValueError(f"{path}:{index}: unknown or priority-tagged stream {row[1]}")
            if row[2] not in ("R", "W"):
                raise ValueError(f"{path}:{index}: invalid request type")
            address = int(row[3], 0)
            if address < 0 or address % 64 or address + 64 > capacity:
                raise ValueError(f"{path}:{index}: unaligned/out-of-capacity address")
            core = 0 if row[1] in ("vlm", "act") else 1
            for offset in range(0, 64, tx_bytes):
                yield issue, core, row[2] == "W", address + offset


def execute(memory, trace, *, issue_width, outstanding, max_cycles):
    if min(issue_width, outstanding, max_cycles) < 1:
        raise ValueError("issue width, outstanding limit and max cycles must be positive")
    iterator = iter(requests(trace, memory.tx_bytes, memory.capacity_bytes))
    head = next(iterator, None)
    if head is None:
        raise ValueError("empty trace")
    cycle, accepted, rejected, completed = 0, 0, 0, 0
    pending, completion_times, latencies = {}, [], []
    stream_counts = {0: 0, 1: 0}
    last_issue_ns = 0.0
    while head is not None or pending:
        for rid, when in memory.completions():
            if rid not in pending:
                raise RuntimeError(f"duplicate or unrecognized callback {rid}")
            issued_at = pending.pop(rid)
            if when < issued_at:
                raise RuntimeError("completion precedes acceptance")
            completion_times.append(when)
            latencies.append((when - issued_at) * memory.tck_ns)
            completed += 1
        if head is None and not pending:
            break
        if cycle >= max_cycles:
            raise RuntimeError(f"cycle budget exhausted: {accepted} accepted, {completed} completed")
        for _ in range(issue_width):
            if head is None or len(pending) >= outstanding:
                break
            issue_ns, core, write, address = head
            if issue_ns > cycle * memory.tck_ns + 1e-9:
                break
            if not memory.send(accepted, write, address, core):
                rejected += 1
                break  # Explicit in-file FIFO head-of-line retry policy.
            pending[accepted] = cycle
            stream_counts[core] += 1
            accepted += 1
            last_issue_ns = issue_ns
            head = next(iterator, None)
        memory.tick()
        cycle += 1
    if accepted != completed:
        raise RuntimeError("accepted/completed request accounting mismatch")
    total_bytes = accepted * memory.tx_bytes
    lo, hi = int(completed * 0.1), int(completed * 0.9)
    duration_ns = (completion_times[hi] - completion_times[lo]) * memory.tck_ns
    if hi <= lo or duration_ns <= 0:
        raise ValueError("too few completions for a trimmed measurement window")
    return {"accepted": accepted, "completed": completed, "rejected_attempts": rejected,
            "cycles": cycle, "tck_ns": memory.tck_ns, "transaction_bytes": memory.tx_bytes,
            "logical_bytes": total_bytes, "stream_transactions": stream_counts,
            "last_offered_issue_ns": last_issue_ns,
            "completion_time_ns": max(completion_times) * memory.tck_ns,
            "makespan_GBps": total_bytes / (cycle * memory.tck_ns),
            "achieved_GBps": (hi - lo) * memory.tx_bytes / duration_ns,
            "measurement_start_ns": completion_times[lo] * memory.tck_ns,
            "measurement_end_ns": completion_times[hi] * memory.tck_ns,
            "latency_p50_ns": float(np.percentile(latencies, 50)),
            "latency_p95_ns": float(np.percentile(latencies, 95))}


def main():
    import yaml
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("traces", type=Path, nargs="+")
    ap.add_argument("--backend", type=Path, default=Path(".native"))
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--issue-width", type=int, default=8)
    ap.add_argument("--outstanding", type=int, default=512)
    ap.add_argument("--max-cycles", type=int, default=20_000_000)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("output directory exists; select a fresh run directory")
    root = args.backend.resolve()
    Ramulator, export_config = load_backend(root)
    config = json.loads(args.config.read_text())
    args.out.mkdir(parents=True)
    expanded_path = args.out / "dram.yaml"
    export_config(config, expanded_path, num_cores=2)
    expanded = yaml.safe_load(expanded_path.read_text())
    device = expanded["memory_system"]["controllers"][0]["dram"]
    import ramulator
    standard = getattr(ramulator.dram, config["standard"])
    # Resolved data rate is Mb/s per DQ; channel_width is aggregate physical DQ bits.
    rate = device["timing"][standard.timing_params.index("rate")]
    peak = config["channels"] * device["channel_width"] / 8 * rate / 1000
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    library = root / "build" / f"libneusim_ramulator_bridge{suffix}"
    source_manifest = root / "source_manifest.json"
    metadata = {"backend": "native Ramulator via NeuSim bridge", "backend_executed": True,
                "config": config, "peak_GBps": peak,
                "source_manifest_sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
                "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "memory_library_sha256": hashlib.sha256((root / "source/third_party/ramulator2" / f"libramulator{suffix}").read_bytes()).hexdigest(),
                "expanded_config_sha256": hashlib.sha256(expanded_path.read_bytes()).hexdigest(),
                "issue_policy": "global in-file FIFO; retry blocked head next cycle; no priority tagging",
                "issue_width_transactions_per_cycle": args.issue_width,
                "max_outstanding_transactions": args.outstanding,
                "measurement": "10%-90% completed-transaction interval (n-1 intervals), plus full makespan",
                "controller": "FRFCFS/Open; per-bank HBM refresh; single-thread real ticks",
                "priority_supported": False,
                "scope": "Simulator calibration only, not physical hardware measurement"}
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    fields = ["benchmark", "peak_GBps", "achieved_GBps", "makespan_GBps", "bytes", "cycles"]
    with (args.out / "measurements.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        for trace in args.traces:
            if trace.stem.startswith("prio_"):
                raise ValueError("backend has no strict-priority support; cannot calibrate prio_leak")
            started = time.monotonic()
            with Ramulator(expanded_path, library=library) as memory:
                report = execute(memory, trace, issue_width=args.issue_width,
                                 outstanding=args.outstanding, max_cycles=args.max_cycles)
                memory.finalize(args.out / f"{trace.stem}_stats.yaml")
            report.update(benchmark=trace.stem, peak_GBps=peak,
                          wall_seconds=time.monotonic() - started,
                          trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
            (args.out / f"{trace.stem}.json").write_text(json.dumps(report, indent=2) + "\n")
            writer.writerow({"benchmark": trace.stem, "peak_GBps": peak,
                             "achieved_GBps": report["achieved_GBps"],
                             "makespan_GBps": report["makespan_GBps"],
                             "bytes": report["logical_bytes"], "cycles": report["cycles"]})
            f.flush()
            print(f"{trace.stem}: {report['achieved_GBps']:.3f}/{peak:.3f} GB/s; "
                  f"{report['completed']} callbacks; {report['wall_seconds']:.2f}s", flush=True)


if __name__ == "__main__":
    main()
