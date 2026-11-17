"""Sanity checks against the closed-form model (ideal DRAM)."""
from vlasim import *
wl = Pi05Workload(); ideal = DRAMModel(eta_seq=1.0, eta_mix=1.0)
FV, WV = wl.vlm_totals(); FD, WD = wl.dit_totals_per_request()
hw = HWConfig(n_cores=4, dram_bw=79e9, sram_mb=128)
util = 90e12 / (3 * hw.core_peak)
ok = True
def check(name, got, exp, tol=0.08):
    global ok
    good = abs(got - exp) / exp <= tol; ok &= good
    print(f"[{'PASS' if good else 'FAIL'}] {name}: sim={got:.4g} expected={exp:.4g}")
# serial: S == L
r = Simulator(hw, MapConfig(mode="serial", vlm_util=util*0.75), wl, ideal).run()
check("serial S==L", r["S_mean"], r["L_mean"], 0.01)
# k=2 batched: DiT weight traffic halves
r = Simulator(hw, MapConfig(vlm_cores=3, dit_stages=2, vlm_util=util, bw_policy="vlm_priority"), wl, ideal).run()
check("k=2 DiT bytes/req = W_D/2", r["dit_GB_per_req"]*1e9, WD/2, 0.03)
S_exp = max(FV/90e12, (WV + WD/2)/79e9)
check("k=2 S vs closed form", r["S_mean"], S_exp)
check("k=2 L vs closed form T_V+2S", r["L_mean"], FV/90e12 + 2*S_exp, 0.10)
# k=2 unbatched ablation: no traffic saving
r = Simulator(hw, MapConfig(vlm_cores=3, dit_stages=2, vlm_util=util, dit_batching=False), wl, ideal).run()
check("k=2 unbatched DiT bytes/req = W_D", r["dit_GB_per_req"]*1e9, WD, 0.03)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
raise SystemExit(0 if ok else 1)
