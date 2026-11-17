"""Verify Case v3 native evidence and report blocked main-case gates explicitly."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import yaml


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p0", type=Path, required=True)
    ap.add_argument("--followup", type=Path, required=True)
    ap.add_argument("--lpddr", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    p0 = json.loads((args.p0 / "p0_report.json").read_text())
    evidence, all_rows = [], []
    groups = [(args.p0, "p0_report.json", "runs"),
              (args.followup, "diagnostic_report.json", "cases"),
              (args.lpddr, "diagnostic_report.json", "cases")]
    for root, report_name, key in groups:
        report_path = root / report_name
        report = json.loads(report_path.read_text())
        manifest_path = root / "experiment_manifest.json"
        assert digest(manifest_path) == report["manifest_sha256"], manifest_path
        manifest = json.loads(manifest_path.read_text())
        assert report["backend_identity"] == p0["backend_identity"]
        for name, expected in manifest["source_hashes"].items():
            path = root / "executed_sources" / name
            if not path.exists():
                path = Path(__file__).parent / "ramulator_bridge" / name
            assert digest(path) == expected, path
        for index, row in enumerate(report[key]):
            raw = json.loads((root / f"run_{index:03d}.json").read_text())
            assert all(row[k] == value for k, value in raw.items()), (root, index)
            assert digest(root / f"run_{index:03d}.yaml") == row["yaml_sha256"]
            trace = args.p0 / "traces" / (row["benchmark"] + ".csv")
            assert digest(trace) == row["trace_sha256"], trace
            n = row["native"]
            assert n["accepted"] == n["completed"] == sum(n["stream_transactions"].values())
            assert n["logical_bytes"] == n["accepted"] * n["transaction_bytes"] == 4 * 2**20
            stats = yaml.safe_load((root / f"run_{index:03d}_stats.yaml").read_text())["memory_system"]
            assert stats["total_num_read_requests"] == n["accepted"]
            assert stats["total_num_write_requests"] == 0
            assert sum(c["num_read_reqs_served"] for c in stats["controller"]) == n["completed"]
            assert sum(c["read_row_hits"] + c["read_row_misses"] + c["read_row_conflicts"] for c in stats["controller"]) == n["completed"]
            if "stream_common_window_GBps" in n:
                assert math.isclose(sum(n["stream_common_window_GBps"].values()), n["achieved_GBps"], abs_tol=1e-9)
            all_rows.append(dict(experiment=root.name, memory=row["memory"], benchmark=row["benchmark"],
                label=row.get("label", "diagnostic"), frontend=row.get("frontend", row.get("frontend_version")),
                mapper=row["mapper"], issue_width=row.get("issue_width", row.get("width")),
                outstanding=row.get("outstanding", 512), refresh=row["refresh"], partition=row.get("partition"),
                bank_group_partition=row.get("bank_group_partition", False), peak_GBps=row["peak_GBps"],
                achieved_GBps=n["achieved_GBps"], makespan_GBps=n["makespan_GBps"],
                effective_fraction=n["achieved_GBps"] / row["peak_GBps"],
                vlm_GBps=n.get("stream_common_window_GBps", {}).get("0"),
                dit_GBps=n.get("stream_common_window_GBps", {}).get("1"),
                isolation_gate=row.get("isolation_gate"), trace_sha256=row["trace_sha256"]))
        evidence.append(dict(path=str(report_path), sha256=digest(report_path), runs=len(report[key])))
    assert digest(args.p0 / "CASE_V3_SPEC.md") == json.loads((args.p0 / "experiment_manifest.json").read_text())["spec_sha256"]
    with (args.out / "p0_sweep.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    mapping_groups = []
    (args.out / "calib").mkdir()
    for memory, width in sorted({(r["memory"], r["issue_width"]) for r in all_rows
                                 if r["mapper"] == "MOP4CLXOR" and r["frontend"] == "per-channel-fifo-rr-v1" and r["refresh"]}):
        selected = [r for r in all_rows if r["memory"] == memory and r["issue_width"] == width
                    and r["mapper"] == "MOP4CLXOR" and r["frontend"] == "per-channel-fifo-rr-v1" and r["refresh"]]
        seq = sorted(r["effective_fraction"] for r in selected if r["benchmark"].startswith("seq_"))
        mix = [r for r in selected if r["benchmark"].startswith("mix_")]
        assert len(seq) == len(mix) == 3
        nominal = seq[1]
        eta_mix = next(r["effective_fraction"] for r in mix if r["benchmark"] == "mix_50") / nominal
        group = dict(memory=memory, issue_width=width, seq_efficiencies=seq,
                     eta_seq_nominal=nominal, eta_mix_balanced=eta_mix,
                     seq_gate="pass_all_seq" if min(seq) >= .8 else "failed_some_seq",
                     calibration_scope="Six saturated-read microbenchmarks only; not a held-out VLA or priority validation")
        mapping_groups.append(group)
        calib = dict(version=f"dram_v3_{memory}_mop4_width{width}",
                     params=dict(eta_seq=nominal, eta_mix=eta_mix, prio_leak=0.0),
                     bounds=dict(eta_seq=[min(seq), max(seq)],
                                 eta_mix=[min(r["effective_fraction"] / nominal for r in mix), max(r["effective_fraction"] / nominal for r in mix)]),
                     params_status=dict(eta_seq="measured", eta_mix="balanced-reference-only", prio_leak="unmeasured_not_validated"),
                     backend_metadata=dict(p0["backend_identity"], backend_executed=True,
                         config=next(r["config"] for r in p0["runs"] if r["memory"] == memory),
                         peak_GBps=selected[0]["peak_GBps"], controller="FRFCFS/Open", refresh="HBMPerBankRefresh" if memory == "M-H256" else "PerBank",
                         addr_mapper="MOP4CLXOR", channel_mapper="CacheLineInterleave", transaction_bytes=32,
                         frontend_version="per-channel-fifo-rr-v1", issue_width=width, max_outstanding=512, priority_supported=False),
                     seq_gate=group["seq_gate"], usable_for_full_case_v3=False,
                     interpretation="Diagnostic calibration; width16/32 explicitly changes the original issue8 setup. Do not transfer original-mapper isolation results to MOP4CLXOR.",
                     evidence=evidence)
        (args.out / "calib" / (calib["version"] + ".json")).write_text(json.dumps(calib, indent=2) + "\n")
    gates = [
        dict(name="original_mapping_efficiency", status="failed", detail=p0["memories"]),
        dict(name="nonblocking_frontend", status="implemented_and_executed", detail="Per-channel FIFO, skip rejected channel; global outstanding512, transaction32 unchanged. HBM seq unchanged versus legacy."),
        dict(name="mapping_followup", status="diagnostic_only", detail=mapping_groups),
        dict(name="exact_lpddr_target_bandwidth", status="unavailable_in_pinned_presets", detail="LPDDR5-6400 x16 yields204.8/409.6 GB/s for16/32 channels; no LPDDR5X preset."),
        dict(name="slicing_on", status="blocked", detail="No verified lowering from row-sliced128x128 hardware into the square-array NeuSim API."),
        dict(name="priority_and_balance_transfer", status="unvalidated", detail="Native FRFCFS has no strict stream priority; no measured priority/balance behavior. Analytical policy exploration must not be labeled measured."),
        dict(name="channel_partition_model", status="not_promoted", detail="No tested p passes all mix ratios. BG isolation success does not establish fixed per-stream channel caps."),
    ]
    output = dict(status="blocked_for_full_case_v3", native_runs=len(all_rows), evidence=evidence, gates=gates,
                  audit_source_sha256=digest(Path(__file__)),
                  spec_sha256=digest(args.p0 / "CASE_V3_SPEC.md"),
                  compute_execution="not_run_in_this_prerequisite_campaign",
                  spec_consistency_notes=[
                      "Expected rule1 requires strict k2<k1 everywhere, whereas rule4 expects equality in the high-bandwidth regime; saturation ties need an explicit exception.",
                      "The1024GB/s narrative says k1=k2=23.5ms, but the supplied table lists k1=27.5 and k2=23.5ms. These cannot both be acceptance targets.",
                      "A bank-group partition on shared channels is not equivalent to a fixed fraction of disjoint channels."],
                  main_sweep_executed=False, frontier_executed=False,
                  interpretation="P0 evidence is complete for the stated diagnostics, not the main Case v3 grid. No fabricated sweep/frontier or final architecture/task/cost claim.")
    (args.out / "status.json").write_text(json.dumps(output, indent=2) + "\n")
    lines = ["# Case v3 主扫描消融状态", "", "P0 和诊断原始数据见 `p0_sweep.csv`、`status.json`。主网格未执行，以下不能视为零收益或通过。", "", "| 必做对照 | 状态 | 原因 |", "| --- | --- | --- |"]
    for name in ("同分配 k=1/2/3", "合批开/关", "公平 serial 对照", "流隔离消融", "策略消融"):
        lines.append(f"| {name} | 未执行主 case | P0 原配置效率失败；诊断映射尚未形成同映射完整隔离校准；slice/策略有独立缺口 |")
    lines += ["", "未生成主网格 `sweep.csv` 或 `frontier.csv`，避免把未执行配置伪装为结果。", "", "此处保留规格中的五项验收，不将上一轮不同硬件配置的 k 消融冒充本轮数据。"]
    (args.out / "ablations.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(status=output["status"], native_runs=len(all_rows), verified_native_accounting=True), indent=2))


if __name__ == "__main__":
    main()
