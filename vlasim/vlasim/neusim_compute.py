"""Compute-only optional provider; strict by default, no implicit DRAM costs."""
import importlib
import hashlib
import json
import math
from pathlib import Path
import sys

from .kernel_shapes import gemms_for_op


class NeuSimTiming:
    def __init__(self, snapshot, workload, *, allow_analytical_siglip=False):
        root = Path(snapshot).resolve()
        if not (root / "source_manifest.json").is_file():
            raise ValueError("a versioned compute snapshot is required")
        source = root / "source"
        self._source = source
        manifest = json.loads((root / "source_manifest.json").read_text())
        for record in manifest["files"]:
            path = (source / record["path"]).resolve()
            if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("compute snapshot hash mismatch: " + record["path"])
        for path in (source, source / "third_party/NeuSim"):
            sys.path.insert(0, str(path))
        module = importlib.import_module("neusim_ramulator.compute")
        if not Path(module.__file__).resolve().is_relative_to(source):
            raise ValueError("an unrelated NeuSim integration is already imported")
        self.factory = module.NeuSimCompute
        self.workload = workload
        self.allow_analytical_siglip = allow_analytical_siglip
        self.models = {}
        self.op_times = {}
        self.fallback_calls = 0
        self.resolved_calls = 0

    def __call__(self, op, group_name, group_peak, hw):
        if hw.array_rows != hw.array_cols or self.workload.c.w_bytes != 2:
            raise NotImplementedError("provider currently requires square arrays and bf16 weights")
        if hw.slice_mode:
            raise NotImplementedError("row-sliced hardware has no verified NeuSim lowering")
        cache_key = (op.name, op.flops, op.util, group_peak, hw.array_rows, hw.freq_hz)
        if cache_key in self.op_times:
            return self.op_times[cache_key]
        try:
            kernels = gemms_for_op(op, self.workload.c, self.workload)
        except NotImplementedError:
            if op.name != "siglip" or not self.allow_analytical_siglip:
                raise
            self.fallback_calls += 1
            duration = op.flops / (op.util * group_peak)
            self.op_times[cache_key] = duration
            return duration
        cores = group_peak / hw.core_peak
        if not math.isclose(cores, round(cores), rel_tol=1e-12) or cores < 1:
            raise ValueError("group peak must represent a whole number of cores")
        key = (round(cores), hw.array_rows, hw.freq_hz)
        if key not in self.models:
            self.models[key] = self.factory(dict(num_sa=key[0], num_vu=key[0], sa_dim=key[1],
                                                 freq_GHz=hw.freq_hz / 1e9,
                                                 use_vu_for_small_matmul=False))
            config_module = importlib.import_module(type(self.models[key].config).__module__)
            if not Path(config_module.__file__).resolve().is_relative_to(self._source / "third_party/NeuSim"):
                raise ValueError("an unrelated NeuSim implementation is already imported")
        backend = self.models[key]
        duration = sum(k.repeats * backend.gemm_ns(k.m, k.n, k.k, "BFLOAT16") for k in kernels) * 1e-9
        self.resolved_calls += 1
        self.op_times[cache_key] = duration
        return duration
