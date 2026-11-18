import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dynamicvla_calibration", ROOT / "scripts/generate_dynamicvla_calibration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_profile_traffic_is_dynamicvla_specific():
    profile_path = ROOT / "publication/dynamicvla_pilot/profile.json"
    profile = json.loads(profile_path.read_text())
    sizes = module.profile_bytes(profile)
    assert sizes["flow_steps"] == 10
    assert sizes["prefix_ops"] == 569
    assert sizes["dit_ops_per_step"] == 140
    assert sizes["prefix_weights"] % 64 == 0
    assert sizes["dit_weights"] % 64 == 0


def test_generator_has_no_pi05_calibration_dependency(tmp_path):
    profile = ROOT / "publication/dynamicvla_pilot/profile.json"
    out = tmp_path / "traces"
    manifest = module.generate(profile, out)
    assert manifest["model"] == "dynamicvla"
    assert "pi05" not in json.dumps(manifest).lower()
    assert (out / "seq_dynamicvla_prefix.csv").exists()
    assert (out / "mix_dynamicvla_k2_batched.csv").exists()
    assert (out / "mix_dynamicvla_k2_unbatched.csv").exists()
    for item in manifest["files"]:
        assert hashlib.sha256((out / item["file"]).read_bytes()).hexdigest() == item["sha256"]


def test_trace_format_and_addresses(tmp_path):
    profile = ROOT / "publication/dynamicvla_pilot/profile.json"
    out = tmp_path / "traces"
    module.generate(profile, out)
    rows = (out / "mix_dynamicvla_k3_batched.csv").read_text().splitlines()
    assert rows
    for row in rows[:100]:
        t, stream, rw, address = row.split(",")
        assert float(t) >= 0
        assert stream in {"vlm", "dit", "kv", "act"}
        assert rw in {"R", "W"}
        assert int(address, 16) % 64 == 0
