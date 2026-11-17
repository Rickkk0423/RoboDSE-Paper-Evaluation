"""pi0.5 workload description at layer granularity.

All structural numbers are ESTIMATES of the OpenPI pi05 configuration
(PaliGemma: SigLIP + Gemma-2B VLM; Gemma-300M action expert with adaRMS).
Verify against the deployed checkpoint before using results in the paper.

Units: FLOPs (1 MAC = 2 FLOPs), bytes.
"""
from dataclasses import dataclass, field


@dataclass
class Pi05Config:
    # --- sequence / schedule ---
    H: int = 16                 # action tokens per request
    flow_steps: int = 10
    prefix_tokens: int = 968    # 3x256 image slots + 200 text (padded); valid ~570
    n_images: int = 3
    img_tokens: int = 256
    # --- VLM (Gemma-2B) ---
    vlm_layers: int = 18
    vlm_width: int = 2048
    vlm_mlp: int = 16384
    vlm_heads: int = 8
    kv_heads: int = 1
    head_dim: int = 256
    siglip_params: float = 0.40e9
    # --- action expert (Gemma-300M) ---
    dit_layers: int = 18
    dit_width: int = 1024
    dit_mlp: int = 4096
    dit_heads: int = 8
    adarms_precomputed: bool = True   # timestep-only conditioning precomputed (exact for fixed schedule)
    # --- precision ---
    w_bytes: float = 2.0        # weight bytes/param (bf16 default=2; INT8/FP8=1 for sensitivity)
    kv_bytes: float = 2.0       # KV element bytes
    act_bytes: float = 2.0


@dataclass
class Op:
    """One schedulable unit of work on a core group."""
    name: str
    flops: float            # useful FLOPs
    util: float             # array utilization for this op (<=1); effective work = flops/util
    dram_bytes: float       # bytes that must cross the DRAM interface
    stream: str             # 'vlm' or 'dit' (for bandwidth policy / accounting)
    weight_bytes: float = 0.0  # portion of dram_bytes that is learned weights (accounting)
    request_ids: tuple[int, ...] = ()  # scheduler annotation for recorded batched operations


class Pi05Workload:
    def __init__(self, cfg: Pi05Config | None = None):
        self.c = cfg or Pi05Config()
        c = self.c
        # VLM per-layer weights (params)
        q = c.vlm_width * c.vlm_heads * c.head_dim
        kv = 2 * c.vlm_width * c.kv_heads * c.head_dim
        o = c.vlm_heads * c.head_dim * c.vlm_width
        ffn = 3 * c.vlm_width * c.vlm_mlp
        self.vlm_layer_params = q + kv + o + ffn
        # DiT per-layer weights (params)
        q = c.dit_width * c.dit_heads * c.head_dim
        kv = 2 * c.dit_width * c.kv_heads * c.head_dim
        o = c.dit_heads * c.head_dim * c.dit_width
        ffn = 3 * c.dit_width * c.dit_mlp
        self.dit_layer_params = q + kv + o + ffn
        self.adarms_layer_params = 2 * c.dit_width * 3 * c.dit_width  # 2 norms, width->3*width
        # prefix KV per layer (bytes) and total
        self.kv_layer_bytes = c.prefix_tokens * 2 * c.kv_heads * c.head_dim * c.kv_bytes
        self.kv_total_bytes = self.kv_layer_bytes * c.vlm_layers
        # VLM per-layer activation working set kept in SHARED SRAM between layers:
        # layer input + output (act_bytes) + FP32 partial sums for the output (FFN computed in
        # intermediate-dim chunks so the T x mlp intermediate never materialises)
        self.vlm_act_bytes = c.prefix_tokens * c.vlm_width * (2 * c.act_bytes + 4)
        # if it does not fit, each layer writes its output to DRAM and reads it back
        self.vlm_spill_layer_bytes = 2 * c.prefix_tokens * c.vlm_width * c.act_bytes

    # ---------------- VLM ----------------
    def vlm_ops(self, kv_on_chip: bool, util: float, act_on_chip: bool = True) -> list[Op]:
        c = self.c
        ops = []
        sig_tokens = c.n_images * c.img_tokens
        ops.append(Op("siglip", 2 * c.siglip_params * sig_tokens, util,
                      c.siglip_params * c.w_bytes, "vlm", c.siglip_params * c.w_bytes))
        T = c.prefix_tokens
        attn = 2 * 2 * T * T * c.vlm_heads * c.head_dim
        for l in range(c.vlm_layers):
            wb = self.vlm_layer_params * c.w_bytes
            kvw = 0.0 if kv_on_chip else self.kv_layer_bytes
            spill = 0.0 if act_on_chip else self.vlm_spill_layer_bytes
            ops.append(Op(f"vlm_l{l}", 2 * self.vlm_layer_params * T + attn, util,
                          wb + kvw + spill, "vlm", wb))
        return ops

    def vlm_totals(self):
        ops = self.vlm_ops(kv_on_chip=True, util=1.0)
        return sum(o.flops for o in ops), sum(o.weight_bytes for o in ops)

    # ---------------- DiT ----------------
    def dit_round_ops(self, batch: int, n_steps: int, kv_on_chip: bool,
                      array_rows: int, slice_mode: bool, resident_frac: float) -> list[Op]:
        """Ops for one DiT round: `batch` requests (one per stage) each advance `n_steps`
        flow steps in layer lockstep. Shared-weight linears are batched (weights read once);
        attention is request-private (each request reads its own prefix KV)."""
        c = self.c
        ops = []
        M = c.H * batch
        util = 1.0 if slice_mode else min(1.0, M / array_rows)
        lin_params = self.dit_layer_params
        if not c.adarms_precomputed:
            lin_params += self.adarms_layer_params  # M=1 matvec, modeled as part of the weight stream
        w_dram = lin_params * c.w_bytes * (1.0 - resident_frac)
        Tk = c.prefix_tokens + c.H
        attn_flops_req = 2 * 2 * c.H * Tk * c.dit_heads * c.head_dim
        for s in range(n_steps):
            for l in range(c.dit_layers):
                ops.append(Op(f"dit_s{s}_l{l}_lin", 2 * lin_params * M, util,
                              w_dram, "dit", w_dram))
                kvr = 0.0 if kv_on_chip else self.kv_layer_bytes * batch
                ops.append(Op(f"dit_s{s}_l{l}_attn", attn_flops_req * batch, util,
                              kvr, "dit", 0.0))
        return ops

    def dit_totals_per_request(self):
        c = self.c
        p = self.dit_layer_params + (0 if c.adarms_precomputed else self.adarms_layer_params)
        lin = 2 * p * c.H * c.dit_layers * c.flow_steps
        Tk = c.prefix_tokens + c.H
        attn = 2 * 2 * c.H * Tk * c.dit_heads * c.head_dim * c.dit_layers * c.flow_steps
        return lin + attn, p * c.w_bytes * c.dit_layers * c.flow_steps
