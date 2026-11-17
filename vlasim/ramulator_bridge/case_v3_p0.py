"""Case v3 prerequisite experiment, with measured gates and no assumed efficiencies."""
import argparse
import hashlib
import json
from math import prod
from pathlib import Path
import shutil
import sys
import time

import yaml

from channel_frontend import VERSION, execute as execute_channels
from gen_traces import micro
from run_native import execute as execute_fifo, load_backend


MEMORIES = {
    "M-H256": dict(standard="HBM2", channels=8, organization="HBM2_2Gb", timing="HBM2_2000Mbps"),
    "M-L256": dict(standard="LPDDR5", channels=16, organization="LPDDR5_8Gb_x16", timing="LPDDR5_6400"),
    "M-L512": dict(standard="LPDDR5", channels=32, organization="LPDDR5_8Gb_x16", timing="LPDDR5_6400"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(config, path, *, refresh=True, mapper="RoBaRaCoCh"):
    from neusim_ramulator.upstream import add_upstream
    add_upstream("RAMULATOR_ROOT", "third_party/ramulator2/python")
    import ramulator as ram
    standard = getattr(ram.dram, config["standard"])
    controller = ram.controller.HBM12 if config["standard"] == "HBM2" else ram.controller.LPDDR5
    refresh_cls = ram.refresh_manager.HBMPerBankRefresh if config["standard"] == "HBM2" else ram.refresh_manager.PerBank
    controllers = []
    for _ in range(config["channels"]):
        device = standard(org_preset=config["organization"], timing_preset=config["timing"])
        controllers.append(controller(dram=device, scheduler=ram.scheduler.FRFCFS(),
            row_policy=ram.row_policy.Open(), addr_mapper=getattr(ram.addr_mapper, mapper)(),
            refresh_manager=(refresh_cls() if refresh else ram.refresh_manager.NoRefresh())))
    expanded = ram.memory_system.GenericDRAM(clock_ratio=1, controllers=controllers,
                                             channel_mapper=ram.channel_mapper.CacheLineInterleave()).to_config()
    device = expanded["controllers"][0]["dram"]
    tx = device.get("data_payload_bytes", standard.internal_prefetch_size * device["channel_width"] // 8)
    capacity = config["channels"] * prod(device["org"]["count"]) // standard.internal_prefetch_size * tx
    path.write_text(yaml.safe_dump(dict(frontend=dict(impl="NeuSimExternal", num_cores=2,
                                                    address_capacity_bytes=capacity), memory_system=expanded), sort_keys=False))
    rate = device["timing"][standard.timing_params.index("rate")]
    counts = device["org"]["count"]
    levels = list(standard.levels)
    bg_index = levels.index("BankGroup")
    column_bits = (counts[-1] // standard.internal_prefetch_size).bit_length() - 1
    bits = [n.bit_length() - 1 for n in counts[1:]]
    bits[-1] = column_bits
    shift = column_bits + sum(n.bit_length() - 1 for n in counts[1:bg_index])
    return dict(peak_GBps=config["channels"] * device["channel_width"] / 8 * rate / 1000,
                transaction_bytes=tx, capacity_bytes=capacity, bg_geometry=(shift, counts[bg_index].bit_length() - 1),
                mop_geometry=(bits, bg_index - 1),
                yaml_sha256=digest(path), expanded=expanded)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.spec, args.out / "CASE_V3_SPEC.md")
    source = Path(__file__).parent
    manifest = dict(spec_sha256=digest(args.spec), execution_date="2026-11-15", spec_date="2026-11-16",
        source_hashes={p.name: digest(p) for p in [Path(__file__), source / "channel_frontend.py", source / "run_native.py", source / "gen_traces.py"]},
        protocol="6 base cases per memory; 3 legacy HBM seq controls; I1 fractions .5/.625/.75 and I2 half-BG against mix25/50/75. Per-condition 95% threshold; universal use requires all ratios to pass. P0 eta_seq >= .80 on all three seq traces. Failed gates block main calibrated claims.",
        issue_width=8, outstanding=512, controller="FRFCFS/Open", transaction_bytes=32,
        frontend=VERSION, trace_total_MiB=4,
        limitations=["LPDDR5X absent in pinned source; LPDDR5-6400 x16 at 16/32 channels is 204.8/409.6 GB/s, not exact 256/512.",
                     "Issue width remains 8 native transactions/cycle; this may cap wide-channel memories.",
                     "No slicing lowering or strict-priority controller validation is supplied by this P0 experiment.",
                     "Isolation is layout/ratio-specific; no universal eta_mix=1 promotion from a selected success."])
    (args.out / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    traces = args.out / "traces"
    traces.mkdir()
    micro(traces, total_mb=4)
    Ramulator, _ = load_backend(args.backend.resolve())
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    library = args.backend.resolve() / "build" / ("libneusim_ramulator_bridge" + suffix)
    identity = dict(source_manifest_sha256=digest(args.backend / "source_manifest.json"),
                    library_sha256=digest(library),
                    memory_library_sha256=digest(args.backend / "source/third_party/ramulator2" / ("libramulator" + suffix)))
    rows, memories = [], {}

    def trial(name, config, trace_name, *, legacy=False, partition=None, bg=False,
              refresh=True, mapper="RoBaRaCoCh", outstanding=512, issue_width=8, label="base"):
        index = len(rows)
        yml = args.out / f"run_{index:03d}.yaml"
        geometry = export(config, yml, refresh=refresh, mapper=mapper)
        trace = traces / (trace_name + ".csv")
        started = time.monotonic()
        with Ramulator(yml, library=library) as memory:
            if memory.tx_bytes != 32:
                raise ValueError("native transaction size differs from frozen protocol")
            kwargs = dict(issue_width=issue_width, outstanding=outstanding, max_cycles=20_000_000)
            result = execute_fifo(memory, trace, **kwargs) if legacy else execute_channels(
                memory, trace, channels=config["channels"], partition=partition,
                bg_geometry=geometry["bg_geometry"] if bg else None, **kwargs)
            memory.finalize(args.out / f"run_{index:03d}_stats.yaml")
        row = dict(memory=name, config=config, benchmark=trace_name, label=label,
                   frontend="global-fifo-v1" if legacy else VERSION, partition=partition,
                   bank_group_partition=bg, refresh=refresh, mapper=mapper,
                   outstanding=outstanding, issue_width=issue_width,
                   frontend_peak_GBps=issue_width * result["transaction_bytes"] / result["tck_ns"],
                   peak_GBps=geometry["peak_GBps"], yaml_sha256=geometry["yaml_sha256"],
                   trace_sha256=digest(trace), wall_seconds=time.monotonic() - started, native=result)
        rows.append(row)
        (args.out / f"run_{index:03d}.json").write_text(json.dumps(row, indent=2) + "\n")
        print(f"{index:03d} {name} {label} {trace_name}: {result['achieved_GBps']:.3f}/{geometry['peak_GBps']:.3f} GB/s", flush=True)
        return row

    for name, config in MEMORIES.items():
        base = [trial(name, config, f"seq_{kb}KB") for kb in (4, 64, 1024)]
        mixed = [trial(name, config, f"mix_{ratio}") for ratio in (25, 50, 75)]
        peak = base[0]["peak_GBps"]
        seq_values = [r["native"]["achieved_GBps"] / peak for r in base]
        seq_nominal = sorted(seq_values)[1]
        eta_mix = mixed[1]["native"]["achieved_GBps"] / peak / seq_nominal
        isolation = []
        for fraction in (.5, .625, .75):
            isolation += [trial(name, config, f"mix_{ratio}", partition=fraction, label="I1") for ratio in (25, 50, 75)]
        isolation += [trial(name, config, f"mix_{ratio}", bg=True, label="I2") for ratio in (25, 50, 75)]
        threshold = .95 * seq_nominal * peak
        for row in isolation:
            row["isolation_gate"] = "pass" if row["native"]["achieved_GBps"] >= threshold else "failed"
        supported = [p for p in (.5, .625, .75) if all(r["isolation_gate"] == "pass" for r in isolation if r["partition"] == p)]
        calib = dict(version="dram_v3_" + name, params=dict(eta_seq=seq_nominal, eta_mix=eta_mix, prio_leak=0.0),
            params_status=dict(eta_seq="measured", eta_mix="balanced-reference-only", prio_leak="unmeasured_not_validated"),
            bounds=dict(eta_seq=[min(seq_values), max(seq_values)],
                        eta_mix=[min(r["native"]["achieved_GBps"] / peak / seq_nominal for r in mixed),
                                 max(r["native"]["achieved_GBps"] / peak / seq_nominal for r in mixed)]),
            backend_metadata=dict(identity, backend_executed=True, config=config, peak_GBps=peak,
                                  frontend_version=VERSION, issue_width=8, max_outstanding=512, priority_supported=False),
            gate="pass" if min(seq_values) >= .8 else "failed_eta_seq", scope="Exploratory saturated all-read fit; not validated VLA capacity or priority calibration")
        (args.out / f"dram_v3_{name}.json").write_text(json.dumps(calib, indent=2) + "\n")
        memories[name] = dict(actual_peak_GBps=peak, eta_seq=seq_values, eta_mix_balanced=eta_mix,
                             seq_gate=calib["gate"], isolation_threshold_GBps=threshold,
                             all_ratios_supported_channel_partitions=supported,
                             bank_group_all_ratios_pass=all(r["isolation_gate"] == "pass" for r in isolation if r["label"] == "I2"))
    config = MEMORIES["M-H256"]
    for kb in (4, 64, 1024):
        trial("M-H256", config, f"seq_{kb}KB", legacy=True, label="legacy_control")
    if memories["M-H256"]["seq_gate"] != "pass":
        trial("M-H256", config, "seq_1024KB", refresh=False, label="diagnostic_no_refresh")
        trial("M-H256", config, "seq_1024KB", mapper="ChRaBaRoCo", label="diagnostic_mapper")
        for limit in (128, 1024, 2048):
            trial("M-H256", config, "seq_1024KB", outstanding=limit, label="diagnostic_outstanding")
        for width in (16, 32):
            trial("M-H256", config, "seq_1024KB", issue_width=width, label="diagnostic_issue_width")
    report = dict(memories=memories, runs=rows, backend_identity=identity,
                  manifest_sha256=digest(args.out / "experiment_manifest.json"),
                  status="p0_failed_main_case_blocked" if any(m["seq_gate"] != "pass" for m in memories.values()) else "p0_seq_pass_other_gates_require_review",
                  transaction_diagnostic="32-byte native payload verified from device/ABI; logical64 splits into2. Changing payload would change physical device semantics, not an admissible tuning knob.")
    (args.out / "p0_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(memories, indent=2), flush=True)


if __name__ == "__main__":
    main()
