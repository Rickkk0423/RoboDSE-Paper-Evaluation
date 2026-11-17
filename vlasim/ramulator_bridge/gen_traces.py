"""Generate DRAM request traces for Ramulator2 calibration / validation.

Two kinds:
  1. micro-benchmarks (fit DRAMModel parameters):
       seq_<size>          single sequential stream, request size sweep           -> eta_seq
       mix_<ratio>         two interleaved sequential streams (VLM-like / DiT-like),
                           at different address regions, byte ratio sweep            -> eta_mix
       rw_<frac>           read/write mix (KV write-back, activation spill)           -> rw penalty (optional)
       prio_<ratio>        same as mix but stream tagged hi/lo, for controllers with
                           priority support                                          -> prio_leak
  2. segment replay (held-out validation): a time window of a vlasim run (record=True), each op's
     bytes emitted at the rate the fluid model assigned it, VLM and DiT in separate address regions.

Output: one line per 64 B request:  <issue_time_ns>,<stream>,<R|W>,<hex addr>
  -> convert to your Ramulator frontend's format (e.g. 'LD 0x..' / 'ST 0x..', or a timed trace).
     Addresses are physical and row-sequential within a stream; keep Ramulator's address mapping
     identical across all runs and record it in the calibration JSON.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

LINE = 64
REGION = {"vlm": 0x0000_0000, "dit": 0x4000_0000, "kv": 0x8000_0000, "act": 0xC000_0000}


def seq_stream(f, stream, nbytes, t0_ns=0.0, rate_Bps=None, rw="R", base=None):
    """emit nbytes sequential requests; rate None = issue back-to-back (time 0, let DRAM pace it)."""
    addr = REGION[stream] if base is None else base
    n = int(nbytes // LINE)
    for i in range(n):
        t = t0_ns + (i * LINE / rate_Bps * 1e9 if rate_Bps else 0.0)
        f.write(f"{t:.1f},{stream},{rw},{addr + i*LINE:#x}\n")
    return addr + n * LINE


def interleave(f, a_stream, b_stream, a_bytes, b_bytes, tag=("vlm", "dit"), bases=None):
    """round-robin interleave two sequential streams with the given byte ratio."""
    na, nb = int(a_bytes // LINE), int(b_bytes // LINE)
    base_a, base_b = bases or (REGION[a_stream], REGION[b_stream])
    ia = ib = 0; acc = 0.0; ratio = na / max(na + nb, 1)
    while ia < na or ib < nb:
        acc += ratio
        if (acc >= 1.0 and ia < na) or ib >= nb:
            f.write(f"0,{tag[0]},R,{base_a + ia*LINE:#x}\n"); ia += 1; acc -= 1.0
        else:
            f.write(f"0,{tag[1]},R,{base_b + ib*LINE:#x}\n"); ib += 1


def blocked_balanced(f, per_stream_bytes, burst_lines, shift_bytes=0):
    """Hold bytes/addresses fixed; alternate equal-sized sequential stream bursts."""
    if (not isinstance(burst_lines, int) or burst_lines <= 0
            or per_stream_bytes <= 0 or per_stream_bytes % LINE
            or shift_bytes < 0 or shift_bytes % LINE):
        raise ValueError("expected positive line-aligned traffic and integer burst size")
    lines = per_stream_bytes // LINE
    for start in range(0, lines, burst_lines):
        # DiT first matches the existing balanced interleave at burst_lines=1.
        for stream, base in (("dit", REGION["dit"] + shift_bytes), ("vlm", REGION["vlm"])):
            for i in range(start, min(start + burst_lines, lines)):
                f.write(f"0,{stream},R,{base + i * LINE:#x}\n")


def micro(outdir, total_mb=64):
    if not math.isfinite(total_mb) or total_mb <= 0:
        raise ValueError("total_mb must be positive")
    tot = int(total_mb * 2**20 // LINE) * LINE
    if tot < LINE:
        raise ValueError("total_mb must cover at least one cache line")
    for kb in (4, 64, 1024):                        # request granularity of a stream (tile size)
        with open(f"{outdir}/seq_{kb}KB.csv", "w") as f:
            emitted = off = 0
            while emitted < tot:
                size = min(kb * 1024, tot - emitted)
                seq_stream(f, "vlm", size, base=REGION["vlm"] + off)
                emitted += size
                off += kb * 1024 * 2  # strided tiles, equal total traffic for every benchmark
    for r in (0.25, 0.5, 0.75):
        with open(f"{outdir}/mix_{int(r*100)}.csv", "w") as f:
            interleave(f, "vlm", "dit", tot * r, tot * (1 - r))
        with open(f"{outdir}/prio_{int(r*100)}.csv", "w") as f:
            interleave(f, "vlm", "dit", tot * r, tot * (1 - r), tag=("lo_vlm", "hi_dit"))
    for w in (0.1, 0.3):
        with open(f"{outdir}/rw_{int(w*100)}.csv", "w") as f:
            n = int(tot // LINE)
            for i in range(n):
                rw = "W" if int((i + 1) * w) > int(i * w) else "R"
                f.write(f"0,{'kv' if rw == 'W' else 'vlm'},{rw},{REGION['kv' if rw=='W' else 'vlm'] + i*LINE:#x}\n")


def segment(outdir, t0_ms, dur_ms, hw, mp, dram=None, n_requests=30):
    """replay a window of a vlasim run: each op's DRAM bytes spread uniformly over its duration."""
    from vlasim import Simulator
    if t0_ms < 0 or dur_ms <= 0:
        raise ValueError("window start must be nonnegative and duration positive")
    r = Simulator(hw, mp, dram=dram).run(n_requests=n_requests, record=True)
    t0, t1 = t0_ms * 1e-3, (t0_ms + dur_ms) * 1e-3
    nxt = {"vlm": REGION["vlm"], "dit": REGION["dit"]}
    lines = []
    for (s, e, g, name, b, reqs) in r["timeline"]:
        if e <= t0 or s >= t1 or b <= 0:
            continue
        rate = b / (e - s)
        a, z = max(s, t0), min(e, t1)
        n = int(rate * (z - a) // LINE)
        for i in range(n):
            t_ns = (a - t0 + i * LINE / rate) * 1e9
            lines.append((t_ns, g, nxt[g])); nxt[g] += LINE
    lines.sort()
    if not lines:
        raise ValueError("selected window contains no DRAM traffic")
    if t1 > max(e for _, e, *_ in r["timeline"]):
        raise ValueError("selected window extends beyond the simulated run")
    path = f"{outdir}/segment_{t0_ms:g}ms_{dur_ms:g}ms.csv"
    with open(path, "w") as f:
        for t, g, ad in lines:
            f.write(f"{t:.1f},{g},R,{ad:#x}\n")
    # the model's prediction for the same window, to compare against Ramulator
    print(f"{path}: {len(lines)} requests; model says the window moves "
          f"{len(lines)*LINE/1e6:.1f} MB in {dur_ms} ms (compare achieved BW / completion time in Ramulator)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["micro", "segment"]); ap.add_argument("--out", default="ramulator_bridge/traces")
    ap.add_argument("--t0_ms", type=float, default=600); ap.add_argument("--dur_ms", type=float, default=2)
    ap.add_argument("--total-mb", type=float, default=64)
    ap.add_argument("--calib", type=Path)
    ap.add_argument("--config", type=Path, help="JSON with hardware and mapping objects (dataclass field names)")
    a = ap.parse_args()
    import os; os.makedirs(a.out, exist_ok=True)
    if a.kind == "micro":
        micro(a.out, a.total_mb)
    else:
        from vlasim import HWConfig, MapConfig, DRAMModel
        cfg = json.loads(a.config.read_text()) if a.config else {}
        segment(a.out, a.t0_ms, a.dur_ms,
                HWConfig(**cfg.get("hardware", {"n_cores": 4, "dram_bw": 200e9, "sram_mb": 32})),
                MapConfig(**cfg.get("mapping", {"vlm_cores": 3, "dit_stages": 2})),
                DRAMModel.from_json(a.calib) if a.calib else None)
    manifest = {"kind": a.kind, "format": "issue_time_ns,stream,R_or_W,hex_address (no header)",
                "line_bytes": LINE, "backend_executed": False,
                "limitations": "Requires backend frontend adapter; segment replay uses uniform per-op rates and all reads, not exact event-level memory timing.",
                "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()},
                "files": []}
    micro_names = ([f"seq_{kb}KB.csv" for kb in (4, 64, 1024)]
                   + [f"{kind}_{ratio}.csv" for kind in ("mix", "prio") for ratio in (25, 50, 75)]
                   + ["rw_10.csv", "rw_30.csv"])
    paths = ([Path(a.out) / name for name in micro_names] if a.kind == "micro"
             else [Path(a.out) / f"segment_{a.t0_ms:g}ms_{a.dur_ms:g}ms.csv"])
    for name in ("calib", "config"):
        source = getattr(a, name)
        if source:
            manifest[name] = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                              "content": json.loads(source.read_text())}
    for path in paths:
        digest, count, writes = hashlib.sha256(), 0, 0
        with path.open("rb") as f:
            for line in f:
                digest.update(line)
                count += 1
                writes += line.split(b",")[2] == b"W"
        manifest["files"].append({"file": path.name, "requests": count,
                                  "bytes": count * LINE, "writes": writes,
                                  "sha256": digest.hexdigest()})
    (Path(a.out) / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
