import math
import hashlib
import json

import pytest

from vlasim.kernel_shapes import gemms_for_op, describe_shapes
from vlasim.workload import Pi05Workload, Pi05Config
from vlasim.neusim_compute import NeuSimTiming
from vlasim import HWConfig


def test_provider_rejects_modified_snapshot_before_import(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "compute.py").write_text("modified source\n")
    (tmp_path / "source_manifest.json").write_text(json.dumps({"files": [{
        "path": "compute.py", "sha256": hashlib.sha256(b"original source\n").hexdigest()
    }]}))
    def unexpected_import(name):
        pytest.fail("modified snapshot must fail before importing " + name)
    monkeypatch.setattr("vlasim.neusim_compute.importlib.import_module", unexpected_import)
    with pytest.raises(ValueError, match="snapshot hash mismatch"):
        NeuSimTiming(tmp_path, Pi05Workload())


@pytest.mark.parametrize("batch", [1, 2, 3])
def test_explicit_gemm_shapes_match_layer_flops(batch):
    wl = Pi05Workload()
    ops = wl.vlm_ops(True, 1)[1:] + wl.dit_round_ops(batch, 2, True, 128, True, 0)
    for op in ops:
        kernels = gemms_for_op(op, wl.c, wl)
        assert all(min(k.m, k.n, k.k, k.repeats) > 0 for k in kernels)
        assert math.isclose(sum(k.flops for k in kernels), op.flops, rel_tol=1e-12)


def test_unresolved_shapes_and_unsupported_ada_norm_fail_closed():
    wl = Pi05Workload()
    with pytest.raises(NotImplementedError, match="SigLIP"):
        gemms_for_op(wl.vlm_ops(True, 1)[0], wl.c, wl)
    wl = Pi05Workload(Pi05Config(adarms_precomputed=False))
    with pytest.raises(NotImplementedError, match="adaRMS"):
        gemms_for_op(wl.dit_round_ops(1, 1, True, 128, True, 0)[0], wl.c, wl)
    assert describe_shapes(wl)[0]["status"] == "unresolved"


def test_provider_rejects_unverified_slicing_and_requires_explicit_fallback():
    provider = NeuSimTiming.__new__(NeuSimTiming)
    provider.workload = Pi05Workload()
    provider.allow_analytical_siglip = False
    provider.fallback_calls = 0
    provider.op_times = {}
    op = provider.workload.vlm_ops(True, 1)[0]
    with pytest.raises(NotImplementedError, match="row-sliced"):
        provider(op, "vlm", HWConfig().peak, HWConfig())
    hw = HWConfig(slice_mode=False)
    with pytest.raises(NotImplementedError, match="SigLIP"):
        provider(op, "vlm", hw.peak, hw)
    provider.allow_analytical_siglip = True
    assert provider(op, "vlm", hw.peak, hw) == op.flops / hw.peak
    assert provider.fallback_calls == 1
    assert provider(op, 'vlm', hw.peak, hw) == op.flops / hw.peak
    assert provider.fallback_calls == 1
    with pytest.raises(NotImplementedError, match='row-sliced'):
        provider(op, 'vlm', hw.peak, HWConfig(slice_mode=True))
