"""Hardware and mapping configuration.

Hardware parameters are fixed at tape-out; mapping parameters are chosen at deployment.
"""
from dataclasses import dataclass


@dataclass
class HWConfig:
    n_cores: int = 4
    array_rows: int = 128
    array_cols: int = 128
    freq_hz: float = 1.0e9
    sram_mb: float = 32.0          # SHARED global SRAM: prefix KV, VLM activation working set,
                                   # adaRMS table, weight-multicast staging, optional DiT residency
    local_kb: float = 1024.0       # PRIVATE per-core SRAM: double-buffered weight tiles, activation
                                   # tile, accumulators (its effect on op time comes from NeuSim)
    dram_bw: float = 100e9         # peak DRAM bandwidth (B/s)
    # supported datapath features
    slice_mode: bool = True        # array can be row-sliced so small-M DiT GEMMs keep PEs busy
    dram_priority: bool = True     # memory controller supports per-stream priority

    @property
    def core_peak(self) -> float:          # FLOP/s per core (1 MAC = 2 FLOP)
        return 2 * self.array_rows * self.array_cols * self.freq_hz

    @property
    def local_min_kb(self) -> float:
        # double-buffered bf16 weight tiles + FP32 accumulator tile for one R x C pass
        return (2 * self.array_rows * self.array_cols * 2 + self.array_rows * self.array_cols * 4) / 1024

    @property
    def peak(self) -> float:
        return self.n_cores * self.core_peak


@dataclass
class MapConfig:
    mode: str = "pipelined"        # 'serial' | 'pipelined'
    vlm_cores: int = 3             # remaining cores go to DiT
    dit_stages: int = 1            # k: flow steps split into k stages; k>=2 implies cross-request batching
    dit_batching: bool = True      # if False with k>=2: stages run separately, weights read per stage (ablation)
    max_wait: float = 0.100        # bounded wait (s) for an incoming request to join a DiT round
    vlm_launch: str = "jit"        # 'periodic': retain observations at r*launch_period_s;
                                   # 'eager': start next VLM as soon as allowed;
                                   # 'jit'  : delay start so VLM finishes when DiT is predicted free
                                   #          (keeps observations fresh instead of queueing them)
    bw_policy: str = "fair"        # 'fair' | 'dit_priority' | 'vlm_priority'
    vlm_util: float = 0.85         # sustained array efficiency for large-M VLM GEMMs
    dit_resident_mb: float = 0.0   # DiT weights pinned in SRAM (never re-fetched)
    kv_on_chip: bool | None = None # None: decided by SRAM capacity
    vlm_queue_max: int = 1         # backpressure: max finished-VLM requests waiting for DiT
    stream_partition: float | None = None  # fixed VLM channel fraction, no borrowing
    launch_period_s: float | None = None  # periodic observations at r*T, starting at zero
    jit_freeze_after: int | None = None   # freeze each predictor at its first N samples' mean
