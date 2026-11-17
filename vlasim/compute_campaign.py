"""Exercise real NeuSim shapes and explicitly labeled hybrid request simulations."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.workload import Pi05Workload
from vlasim.kernel_shapes import describe_shapes
from vlasim.neusim_compute import NeuSimTiming


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    wl = Pi05Workload()
    shapes = describe_shapes(wl)
    strict = NeuSimTiming(args.snapshot, wl)
    siglip = wl.vlm_ops(True, 1)[0]
    try:
        hw = HWConfig(slice_mode=False)
        strict(siglip, "vlm", hw.peak, hw)
    except NotImplementedError:
        strict_gate = "blocked_unresolved_siglip"
    else:
        raise RuntimeError("strict provider silently accepted unresolved shapes")
    provider = NeuSimTiming(args.snapshot, wl, allow_analytical_siglip=True)
    results = []
    for cores in (1, 2, 4, 8):
        for mode in (("serial", 1), ("pipelined", 2)) if cores >= 2 else (("serial", 1),):
            hw = HWConfig(n_cores=cores, local_kb=2048, dram_bw=256e9, dram_priority=False, slice_mode=False)
            mp = MapConfig(mode=mode[0], vlm_cores=max(1, cores - 1), dit_stages=mode[1])
            for requests in (30, 120):
                r = Simulator(hw, mp, wl=wl, dram=DRAMModel.from_json(args.calib), compute_time_fn=provider).run(
                    n_requests=requests, warmup=max(6, requests // 5))
                results.append(dict(cores=cores, mode=mode[0], stages=mode[1], requests=requests,
                                    hardware=asdict(hw), mapping=asdict(mp),
                                    L_ms=r["L_mean"] * 1e3, S_ms=r["S_mean"] * 1e3,
                                    sram_ok=r["sram_ok"]))
    manifest = args.snapshot / "source_manifest.json"
    report = dict(shapes=shapes, strict_gate=strict_gate, hybrid_results=results,
                  neuSim_shape_evaluations=sum(m.calls for m in provider.models.values()),
                  resolved_op_calls=provider.resolved_calls, analytical_siglip_calls=provider.fallback_calls,
                  compute_snapshot_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                  source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                 (Path(__file__), Path(__file__).parent / "vlasim/kernel_shapes.py",
                                  Path(__file__).parent / "vlasim/neusim_compute.py")},
                  calibration=json.loads(args.calib.read_text()),
                  scope="Explicit estimated GEMMs through real NeuSim on unsliced arrays, small-matmul VU lowering disabled. SigLIP fallback explicitly enabled. Vector/norm costs absent; head GEMMs sequential; no calibrated SRAM/NoC/silicon model. Not final compute validation.")
    (args.out / "compute_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("strict_gate", "neuSim_shape_evaluations", "analytical_siglip_calls")}, indent=2))


if __name__ == "__main__":
    main()
