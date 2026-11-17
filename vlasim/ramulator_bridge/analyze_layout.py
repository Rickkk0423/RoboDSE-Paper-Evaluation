"""Join backend counters to layout experiments for diagnostics, never prediction."""
import argparse
import hashlib
import json
from pathlib import Path

def summarize_channels(stats):
    channels = stats["memory_system"]["controller"]
    if not isinstance(channels, list) or not channels:
        raise ValueError("expected nonempty native channel list")
    counts = {key: sum(c[key] for c in channels)
              for key in ("read_row_hits", "read_row_misses", "read_row_conflicts", "num_read_reqs")}
    classified = sum(counts[k] for k in ("read_row_hits", "read_row_misses", "read_row_conflicts"))
    if classified != counts["num_read_reqs"] or classified <= 0:
        raise ValueError("native row classification does not account for all reads")
    return {**counts, "row_hit_fraction": counts["read_row_hits"] / classified,
            "row_conflict_fraction": counts["read_row_conflicts"] / classified,
            "mean_channel_read_queue": sum(c["read_queue_len_avg"] for c in channels) / len(channels),
            "request_weighted_read_latency_cycles": sum(c["read_latency"] for c in channels) / classified,
            "channels": len(channels)}


def main():
    import yaml

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("campaign", type=Path)
    args = ap.parse_args()
    output = args.campaign / "counter_report.json"
    if output.exists():
        ap.error("counter report exists; do not overwrite evidence")
    report = json.loads((args.campaign / "layout_report.json").read_text())
    rows = []
    stat_hashes = {}
    for case in report["cases"]:
        path = args.campaign / "native" / (case["case"] + "_stats.yaml")
        stat_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        counters = summarize_channels(yaml.safe_load(path.read_text()))
        if counters["num_read_reqs"] != case["native"]["completed"]:
            raise ValueError(f"native completion/counter mismatch: {case['case']}")
        rows.append({k: case[k] for k in ("case", "shift_bytes", "ratio_pct", "size_mib", "split", "measured_GBps", "error_pct")} | counters)
    output.write_text(json.dumps({"scope": "Post-execution diagnostic counters; unavailable to current analytical DSE. Not fit inputs or causal proof.",
                                  "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                  "layout_report_sha256": hashlib.sha256((args.campaign / "layout_report.json").read_bytes()).hexdigest(),
                                  "stats_sha256": stat_hashes,
                                  "cases": rows}, indent=2) + "\n")
    print(f"Validated and joined native counters for {len(rows)} cases")


if __name__ == "__main__":
    main()
