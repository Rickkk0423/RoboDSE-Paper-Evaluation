"""Replay windows selected to cover isolated VLM/DiT and full batched overlap."""
import argparse
from dataclasses import asdict
import itertools
import json
from pathlib import Path
import subprocess
import sys

from gen_traces import segment
from vlasim import Simulator, HWConfig, MapConfig, DRAMModel


def select_window(timeline, groups, duration, steady_start, steady_end, min_batch=1):
    events = []
    for index, (start, end, group, _, traffic, reqs) in enumerate(timeline):
        if traffic <= 0 or (group == "dit" and len(reqs) < min_batch):
            continue
        events.extend([(start, 1, group, index), (end, -1, group, index)])
    active, previous, choices = {}, 0.0, []
    required = set(groups)
    for now, same_time in itertools.groupby(sorted(events), key=lambda event: event[0]):
        lo, hi = max(previous, steady_start), min(now, steady_end)
        if set(active) == required and hi - lo >= duration:
            choices.append((hi - lo, lo, hi))
        for _, action, group, index in same_time:
            if action == -1:
                if active.get(group) == index:
                    active.pop(group)
            else:
                active[group] = index
        previous = now
    if not choices:
        raise ValueError(f"no steady window for groups={groups}, min_batch={min_batch}")
    _, start, end = max(choices)
    return (start + end - duration) / 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("calib", type=Path)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("output exists; choose a new validation directory")
    args.out.mkdir(parents=True)
    dram = DRAMModel.from_json(args.calib)
    calibration = json.loads(args.calib.read_text())
    if json.loads(args.config.read_text()) != calibration["backend_metadata"]["config"]:
        raise ValueError("validation DRAM configuration differs from calibration")
    peak = calibration["backend_metadata"]["peak_GBps"] * 1e9
    hw = HWConfig(n_cores=8, dram_bw=peak, sram_mb=32, local_kb=2048, dram_priority=False)
    cases = [("vlm_only", MapConfig(mode="serial"), ("vlm",), 1),
             ("dit_only", MapConfig(mode="serial"), ("dit",), 1)]
    cases.extend((f"overlap_k{k}", MapConfig(vlm_cores=6, dit_stages=k), ("vlm", "dit"), k)
                 for k in (1, 2, 3))
    reports = []
    for name, mp, groups, min_batch in cases:
        result = Simulator(hw, mp, dram=dram).run(n_requests=40, record=True)
        duration = 20e-6
        start = select_window(result["timeline"], groups, duration,
                              result["trace"][0][0], result["trace"][-1][1], min_batch)
        directory = args.out / name
        directory.mkdir()
        segment(directory, start * 1e3, duration * 1e3, hw, mp, dram, n_requests=40)
        trace = next(directory.glob("segment_*.csv"))
        native = directory / "native"
        subprocess.run([sys.executable, str(Path(__file__).with_name("run_native.py")), str(trace),
                        "--backend", str(args.backend), "--config", str(args.config), "--out", str(native)], check=True)
        measured = json.loads((native / f"{trace.stem}.json").read_text())
        actual = {group for group, count in measured["stream_transactions"].items() if count}
        expected = {"0" if g == "vlm" else "1" for g in groups}
        if actual != expected:
            raise RuntimeError(f"coverage mismatch for {name}: {actual} != {expected}")
        error = (measured["completion_time_ns"] / (duration * 1e9) - 1) * 100
        reports.append({"case": name, "hardware": asdict(hw), "mapping": asdict(mp),
                        "minimum_dit_batch": min_batch, "groups": list(groups),
                        "model_window_ns": duration * 1e9, "native": measured,
                        "timing_error_pct": error, "within_10pct": abs(error) <= 10})
    report = {"calibration": calibration, "cases": reports,
              "gate": "pass_for_paced_replay_only" if all(r["within_10pct"] for r in reports) else "failed",
              "limitations": "Paced per-op all-read replay, not independent end-to-end validation; full overlap batch checked against simulator timeline."}
    (args.out / "coverage_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"gate": report["gate"], "errors_pct": {r["case"]: r["timing_error_pct"] for r in reports}}, indent=2))


if __name__ == "__main__":
    main()
