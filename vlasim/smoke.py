from vlasim import *
wl = Pi05Workload()
def show(tag, hw, mp):
    r = Simulator(hw, mp, wl).run()
    print(f"{tag:34s} L={r['L_mean']*1e3:6.1f} (p95 {r['L_p95']*1e3:5.1f})  S={r['S_mean']*1e3:6.1f}  "
          f"DRAM/req={r['dram_GB_per_req']:.2f}GB (DiT {r['dit_GB_per_req']:.2f})  "
          f"busy V/D={r['vlm_busy']:.2f}/{r['dit_busy']:.2f}")
hw = HWConfig(n_cores=4, dram_bw=100e9, sram_mb=128)
show("serial", hw, MapConfig(mode="serial"))
for launch in ("eager", "jit"):
    show(f"pipe k=1 {launch}", hw, MapConfig(vlm_cores=3, dit_stages=1, vlm_launch=launch))
for k in (2, 3):
    show(f"pipe k={k} batched", hw, MapConfig(vlm_cores=3, dit_stages=k))
    show(f"pipe k={k} NOT batched (ablation)", hw, MapConfig(vlm_cores=3, dit_stages=k, dit_batching=False))
show("pipe k=2 batched dit_priority", hw, MapConfig(vlm_cores=3, dit_stages=2, bw_policy="dit_priority"))
