"""Area / energy model.  ALL CONSTANTS ARE PLACEHOLDERS — replace with synthesis results
(MAC array, vector unit, NoC), CACTI (SRAM) and LPDDR PHY / energy-per-bit data for your node.
"""
from dataclasses import dataclass
from .hw import HWConfig


@dataclass
class CostModel:
    core_mm2: float = 4.0            # one 128x128 bf16 core (FP32 accumulate) incl. local buffers + vector unit (placeholder)
    sram_mm2_per_mb: float = 0.6     # global SRAM incl. periphery (placeholder; CACTI)
    phy_mm2_per_100gbs: float = 3.0  # DRAM PHY/controller area per 100 GB/s (placeholder)
    pj_per_mac: float = 0.6          # bf16 MAC incl. local data movement (placeholder)
    pj_per_dram_bit: float = 4.0     # LPDDR5-class access energy (placeholder)
    static_w_per_mm2: float = 0.01   # leakage density (placeholder)

    def area(self, hw: HWConfig) -> float:
        return (hw.n_cores * self.core_mm2 * (hw.array_rows * hw.array_cols) / (128 * 128)
                + hw.sram_mb * self.sram_mm2_per_mb                       # shared
                + hw.n_cores * hw.local_kb / 1024 * self.sram_mm2_per_mb  # private, per core
                + hw.dram_bw / 100e9 * self.phy_mm2_per_100gbs)

    def energy_per_req(self, hw: HWConfig, flops: float, dram_bytes: float, S: float) -> float:
        dyn = flops / 2 * self.pj_per_mac * 1e-12 + dram_bytes * 8 * self.pj_per_dram_bit * 1e-12
        static = self.static_w_per_mm2 * self.area(hw) * S   # one refresh interval of leakage
        return dyn + static
