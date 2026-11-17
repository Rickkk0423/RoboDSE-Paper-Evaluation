"""Explicit GEMMs for existing aggregate ops; unresolved work fails closed."""
from dataclasses import asdict, dataclass
import math
import re


@dataclass(frozen=True)
class GEMM:
    name: str
    m: int
    n: int
    k: int
    repeats: int = 1

    @property
    def flops(self):
        return 2 * self.m * self.n * self.k * self.repeats


def _linears(m, width, mlp, heads, kv_heads, dim):
    return [GEMM("q", m, heads * dim, width),
            GEMM("k", m, kv_heads * dim, width), GEMM("v", m, kv_heads * dim, width),
            GEMM("out", m, width, heads * dim), GEMM("gate", m, mlp, width),
            GEMM("up", m, mlp, width), GEMM("down", m, width, mlp)]


def _batch(flops, per_request):
    value = flops / per_request
    if not math.isfinite(value) or value < 1 or not math.isclose(value, round(value), rel_tol=1e-12):
        raise ValueError("aggregate FLOPs do not identify a whole batch")
    return round(value)


def gemms_for_op(op, cfg, workload):
    if op.name == "siglip":
        raise NotImplementedError("SigLIP aggregate parameter count does not specify its kernel shapes")
    if re.fullmatch(r"vlm_l\d+", op.name):
        t = cfg.prefix_tokens
        kernels = _linears(t, cfg.vlm_width, cfg.vlm_mlp, cfg.vlm_heads, cfg.kv_heads, cfg.head_dim)
        kernels += [GEMM("qk", t, t, cfg.head_dim, cfg.vlm_heads),
                    GEMM("av", t, cfg.head_dim, t, cfg.vlm_heads)]
    elif re.fullmatch(r"dit_s\d+_l\d+_lin", op.name):
        if not cfg.adarms_precomputed:
            raise NotImplementedError("non-precomputed adaRMS needs separate timestep matrix shapes")
        batch = _batch(op.flops, 2 * workload.dit_layer_params * cfg.H)
        kernels = _linears(cfg.H * batch, cfg.dit_width, cfg.dit_mlp, cfg.dit_heads, cfg.kv_heads, cfg.head_dim)
    elif re.fullmatch(r"dit_s\d+_l\d+_attn", op.name):
        tk = cfg.prefix_tokens + cfg.H
        batch = _batch(op.flops, 4 * cfg.H * tk * cfg.dit_heads * cfg.head_dim)
        kernels = [GEMM("qk", cfg.H, tk, cfg.head_dim, cfg.dit_heads * batch),
                   GEMM("av", cfg.H, cfg.head_dim, tk, cfg.dit_heads * batch)]
    else:
        raise NotImplementedError("unknown op: " + op.name)
    if not math.isclose(sum(k.flops for k in kernels), op.flops, rel_tol=1e-12):
        raise ValueError("explicit GEMM FLOPs disagree with aggregate op")
    return kernels


def describe_shapes(workload):
    ops = workload.vlm_ops(True, 1.0) + workload.dit_round_ops(1, 1, True, 128, True, 0)
    result = []
    for op in ops:
        try:
            kernels = gemms_for_op(op, workload.c, workload)
            result.append(dict(op=op.name, status="explicit_estimated_shapes", flops=op.flops,
                               kernels=[asdict(k) for k in kernels]))
        except NotImplementedError as error:
            result.append(dict(op=op.name, status="unresolved", reason=str(error)))
    return result
