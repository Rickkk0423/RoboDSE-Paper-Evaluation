"""Generate DynamicVLA-specific Ramulator calibration traces.

The traces are derived from the measured DynamicVLA operator profile rather
than from the frozen Pi0.5 micro-trace sizes.  They are deliberately kept in a
separate output tree and carry the source profile hash in ``manifest.json``.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

LINE = 64
REGION = {"vlm": 0x0000_0000, "dit": 0x4000_0000,
          "kv": 0x8000_0000, "act": 0xC000_0000}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aligned(value):
    return max(LINE, int(math.ceil(float(value) / LINE)) * LINE)


def emit_stream(path, streams, *, rw="R", spacing_ns=0.0):
    """Emit a deterministic round-robin stream list.

    ``streams`` is a list of ``(name, bytes)``.  Each stream uses an isolated
    address region.  Timestamps are intentionally zero unless a paced trace is
    requested; native calibration then measures the controller's saturation
    behavior under the same issue policy used by the existing bridge.
    """
    counters = {name: 0 for name, _ in streams}
    remaining = {name: aligned(size) // LINE for name, size in streams}
    order = [name for name, _ in streams]
    issued = 0
    with path.open("w") as out:
        while any(remaining.values()):
            for name in order:
                if remaining[name] <= 0:
                    continue
                address = REGION[name] + counters[name] * LINE
                timestamp = issued * spacing_ns
                out.write(f"{timestamp:.1f},{name},{rw},{address:#x}\n")
                counters[name] += 1
                remaining[name] -= 1
                issued += 1
    return issued


def profile_bytes(profile):
    prefix = [o for o in profile["operations"] if o["phase"] == "prefix"]
    dit = [o for o in profile["operations"] if o["phase"] == "dit"]
    steps = profile["checkpoint_config"]["num_steps"]
    if not prefix or not dit or len(dit) % steps:
        raise ValueError("profile does not contain a complete prefix/DiT trace")
    per_step = len(dit) // steps
    step = dit[:per_step]
    if any(dit[i * per_step:(i + 1) * per_step] != step for i in range(steps)):
        raise ValueError("per-step DynamicVLA traces differ; calibration needs explicit lowering")
    # The workload adapter uses BF16 for modeled weight/KV traffic.  Keep the
    # conversion explicit here so the calibration input is auditable.
    prefix_weights = sum(o["weight_elements"] * 2 for o in prefix)
    dit_weights = sum(o["weight_elements"] * 2 for o in step)
    kv_bytes = profile["kv_cache"]["runtime_bytes"]
    activation_bytes = sum(math.prod(o["output_shape"]) * 4 for o in prefix)
    return dict(prefix_weights=aligned(prefix_weights), dit_weights=aligned(dit_weights),
                kv_bytes=aligned(kv_bytes), activation_bytes=aligned(activation_bytes),
                flow_steps=steps, prefix_ops=len(prefix), dit_ops_per_step=len(step),
                weight_precision="BF16 target assumption", kv_precision="BF16 target assumption")


def generate(profile_path, out, sample_mb=64):
    profile = json.loads(profile_path.read_text())
    sizes = profile_bytes(profile)
    if sample_mb <= 0:
        raise ValueError("sample_mb must be positive")
    # Native calibration needs a saturated representative stream, not a full
    # model replay. Keep the profile-derived ratios while bounding storage.
    sample_bytes = int(sample_mb * 2**20 // LINE) * LINE

    def sampled(value):
        return min(aligned(value), sample_bytes)

    sampled_sizes = dict(sizes)
    for key in ("prefix_weights", "dit_weights", "kv_bytes", "activation_bytes"):
        sampled_sizes[key] = sampled(sizes[key])
    out.mkdir(parents=True, exist_ok=True)
    files = []

    def add(name, streams, rw="R", spacing_ns=0.0, purpose=""):
        path = out / f"{name}.csv"
        requests = emit_stream(path, streams, rw=rw, spacing_ns=spacing_ns)
        files.append({"file": path.name, "requests": requests, "bytes": requests * LINE,
                      "streams": [{"name": n, "bytes": aligned(b)} for n, b in streams],
                      "purpose": purpose, "sha256": sha256(path)})

    add("seq_dynamicvla_prefix", [("vlm", sampled_sizes["prefix_weights"])],
        purpose="DynamicVLA prefix weight stream")
    add("seq_dynamicvla_dit", [("dit", sampled_sizes["dit_weights"])],
        purpose="one DynamicVLA DiT denoising-step weight stream")
    add("seq_dynamicvla_kv", [("kv", sampled_sizes["kv_bytes"])],
        rw="W", purpose="DynamicVLA KV write-back diagnostic")
    for k in (1, 2, 3):
        # A batched linear stage shares one weight stream while attention/KV is
        # private per chunk.  The trace is a controller-level traffic probe,
        # not an assertion that all operator traffic is perfectly tiled.
        add(f"mix_dynamicvla_k{k}_batched",
            [("vlm", sampled_sizes["prefix_weights"]),
             ("dit", sampled_sizes["dit_weights"]),
             ("kv", sampled_sizes["kv_bytes"] * k)],
            purpose=f"DynamicVLA k={k} batched weight/KV mix")
        if k > 1:
            add(f"mix_dynamicvla_k{k}_unbatched",
                [("vlm", sampled_sizes["prefix_weights"]),
                 ("dit", sampled_sizes["dit_weights"] * k),
                 ("kv", sampled_sizes["kv_bytes"] * k)],
                purpose=f"DynamicVLA k={k} unbatched control")
    for ratio in (25, 50, 75):
        vlm = sampled_sizes["prefix_weights"] * ratio / 100
        dit = sampled_sizes["dit_weights"] * (100 - ratio) / 100
        add(f"mix_dynamicvla_{ratio}", [("vlm", vlm), ("dit", dit)],
            purpose=f"DynamicVLA VLM/DiT ratio {ratio}/{100-ratio}")
    add("rw_dynamicvla_kv_10", [("vlm", sampled_sizes["prefix_weights"] * 9),
                                ("kv", sampled_sizes["kv_bytes"])], rw="R",
        purpose="10 percent KV/activation write diagnostic")

    manifest = {
        "schema": 1,
        "model": "dynamicvla",
        "source_profile": str(profile_path.resolve()),
        "profile_sha256": sha256(profile_path),
        "line_bytes": LINE,
        "address_regions": {k: hex(v) for k, v in REGION.items()},
        "traffic_basis": sizes,
        "trace_sample_mb_per_stream": sample_mb,
        "native_backend_scope": "Ramulator controller calibration only; not silicon measurement",
        "priority": "unsupported by native bridge; no priority traces generated",
        "files": files,
        "limitations": [
            "BF16 traffic is a target mapping assumption for a mixed-precision checkpoint.",
            "KV and activation traffic are aggregate diagnostics, not event-level traces.",
            "Weight sharing represents the intended cross-chunk batching organization.",
            "No Pi0.5 calibration file is read or modified by this generator.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--profile", type=Path,
                    default=root / "publication/dynamicvla_pilot/profile.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sample-mb", type=float, default=64.0)
    args = ap.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        ap.error("output exists and is non-empty; choose a new calibration directory")
    print(json.dumps(generate(args.profile, args.out, args.sample_mb), indent=2))


if __name__ == "__main__":
    main()
