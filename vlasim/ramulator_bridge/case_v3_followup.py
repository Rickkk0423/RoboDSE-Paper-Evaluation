"""Frozen diagnostic contrasts after the Case v3 P0 efficiency gate failed."""
import argparse
import json
from pathlib import Path
import sys

from case_v3_p0 import MEMORIES, digest, export
from channel_frontend import VERSION, execute
from run_native import execute as execute_fifo, load_backend


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", type=Path, required=True)
    ap.add_argument("--p0", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lpddr-mapping", action="store_true", help="new LPDDR5 mapper/width diagnostic set")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = [dict(memory="M-H256", benchmark=f"{kind}_{value}", mapper="MOP4CLXOR", width=8, legacy=False, refresh=True)
             for kind, values in (("seq", ("4KB", "64KB", "1024KB")), ("mix", ("25", "50", "75"))) for value in values]
    cases += [dict(memory="M-H256", benchmark=f"seq_{value}KB", mapper="MOP4CLXOR", width=8, legacy=True, refresh=True) for value in (4, 64, 1024)]
    cases += [dict(memory="M-H256", benchmark="seq_1024KB", mapper="MOP4CLXOR", width=8, legacy=False, refresh=False)]
    cases += [dict(memory="M-L512", benchmark=f"seq_{value}KB", mapper="RoBaRaCoCh", width=width, legacy=False, refresh=True) for width in (16, 32) for value in (4, 64, 1024)]
    if args.lpddr_mapping:
        cases = [dict(memory=memory, benchmark=f"{kind}_{value}", mapper="MOP4CLXOR", width=width, legacy=False, refresh=True)
                 for memory, widths in (("M-L256", (8,)), ("M-L512", (8, 16, 32)))
                 for width in widths
                 for kind, values in (("seq", ("4KB", "64KB", "1024KB")), ("mix", ("25", "50", "75"))) for value in values]
    manifest = dict(cases=cases, p0_sha256=digest(args.p0 / "p0_report.json"),
                    source_hashes={p.name: digest(p) for p in [Path(__file__), Path(__file__).with_name("case_v3_p0.py"), Path(__file__).with_name("channel_frontend.py")]},
                    lpddr_mapping=args.lpddr_mapping,
                    protocol="Diagnostic only: MOP4CLXOR distributes lower address bits across bank hierarchy; hold controller/outstanding constant. Wide LPDDR issue16/32 tests the known 204.8GB/s injector ceiling. All cases frozen before execution; no DSE promotion.")
    (args.out / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    Ramulator, _ = load_backend(args.backend.resolve())
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    library = args.backend.resolve() / "build" / ("libneusim_ramulator_bridge" + suffix)
    results = []
    for index, case in enumerate(cases):
        config = MEMORIES[case["memory"]]
        path = args.out / f"run_{index:03d}.yaml"
        geometry = export(config, path, refresh=case["refresh"], mapper=case["mapper"])
        trace = args.p0 / "traces" / (case["benchmark"] + ".csv")
        with Ramulator(path, library=library) as memory:
            kwargs = dict(issue_width=case["width"], outstanding=512, max_cycles=20_000_000)
            native = execute_fifo(memory, trace, **kwargs) if case["legacy"] else execute(memory, trace, channels=config["channels"], **kwargs)
            memory.finalize(args.out / f"run_{index:03d}_stats.yaml")
        row = dict(case, peak_GBps=geometry["peak_GBps"], native=native,
                   eta_seq_or_mixed_fraction=native["achieved_GBps"] / geometry["peak_GBps"],
                   frontend_version="global-fifo-v1" if case["legacy"] else VERSION,
                   trace_sha256=digest(trace), yaml_sha256=digest(path))
        results.append(row)
        (args.out / f"run_{index:03d}.json").write_text(json.dumps(row, indent=2) + "\n")
        print(f"{index:03d} {case}: {native['achieved_GBps']:.3f} GB/s", flush=True)
    (args.out / "diagnostic_report.json").write_text(json.dumps(dict(
        manifest_sha256=digest(args.out / "experiment_manifest.json"), cases=results,
        backend_identity=json.loads((args.p0 / "p0_report.json").read_text())["backend_identity"],
        scope="Diagnostic contrasts, no DSE promotion or calibrated main sweep"), indent=2) + "\n")


if __name__ == "__main__":
    main()
