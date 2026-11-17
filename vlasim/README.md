# vlasim: request-level hardware simulator for VLA inference (π0.5): produces L and S

A skeleton for the "NeuSim + analytical DRAM layer calibrated against Ramulator" flow.
Everything runs in pure Python. One configuration takes about 40 ms, and the example DSE
(3648 configurations) takes about 1 min on 2 cores.

## Layout

| File | Role |
|---|---|
| `vlasim/workload.py` | π0.5 layer-level workload (VLM, DiT linear + private attention). **Structural numbers are estimates — verify against the checkpoint.** |
| `vlasim/hw.py` | `HWConfig` (tape-out parameters: cores, arrays, PRIVATE per-core SRAM `local_kb`, SHARED SRAM `sram_mb`, DRAM BW) and `MapConfig` (deployment mapping) |
| `vlasim/dram.py` | Fluid DRAM sharing layer: η_seq, η_mix, fair / priority water-filling. **Parameters to be calibrated with Ramulator2.** |
| `vlasim/sim.py` | Request-level discrete-event simulator (L, S, DRAM traffic, utilization) |
| `vlasim/cost.py` | Area and energy model. **All constants are placeholders.** |
| `vlasim/dse.py` | Hardware × mapping enumeration, SRAM feasibility pruning, parallel evaluation, CSV output |
| `run_sweep.py` | Full sweep → `data/sweep_LS.csv`, plus one per-request timeline → `data/trace_example.csv` |
| `analysis/` | **Downstream, not imported by the simulator**: success surface and task-aware selection, to be built on the sweep CSV later |
| `tests_check.py` | Sanity checks against the closed-form model |
| `smoke.py` | Side-by-side comparison of execution organizations |

## Execution organizations

- `mode="serial"`: one request at a time. VLM and DiT each use **all** cores. This is the latency-oriented baseline.
- `mode="pipelined", dit_stages=1`: VLM and DiT groups run concurrently on disjoint cores, with a decoupled hand-off.
- `mode="pipelined", dit_stages=k≥2`: the flow steps are split into k stages, with one request per stage.
  Each DiT round advances every in-flight request by one stage, in layer lockstep.
  **Shared-weight linears are batched across requests, so weights are fetched once per round.**
  Attention stays private to each request.
  `dit_batching=False` is the ablation where the stages run back-to-back and each fetches its own weights.
- `vlm_launch="jit"` delays the VLM start so that its output arrives when the DiT is predicted to be free, which keeps observations fresh.
  `"eager"` starts the VLM as soon as backpressure allows.
- `max_wait`: bounded wait for an incoming request to join a DiT round. When it expires, the round runs without it (singleton fallback).
- `bw_policy`: `fair` | `vlm_priority` | `dit_priority` (strict priority) | `balance` (progress-aware prototype: at every event, split bandwidth so that the current VLM request and the current DiT round are predicted to finish together, which gives the slower stage more bandwidth; see `DRAMModel.balance_targets`).

Definitions:
- L = chunk completion time − observation time. The observation is taken when that request's VLM starts.
- S = interval between successive completions. Adoption is in order and every chunk is adopted.
- Warm-up and drain requests are excluded from the statistics.

## Outputs (per configuration)

- L: mean / std / p50 / p95 / max
- S: mean / std / p50 / p95 / max
- DRAM GB per request (total and DiT)
- VLM and DiT group busy fractions
- whether KV is kept on chip, and SRAM feasibility
- area and energy (placeholder constants)
- `trace`: per-request (observation time, chunk-ready time) for steady state. Use it for action-age traces or for closed-loop replay instead of only the means.

The workload is currently deterministic, so std = 0. Jitter will appear once variable prefix lengths and DRAM noise are added (TODO).

## Integration points

- **NeuSim**: pass `compute_time_fn(op, group, group_peak, hw)` to `Simulator` so that per-op compute time comes from NeuSim.
  `Op.dram_bytes` can also be replaced by NeuSim's memory traffic.
- **Ramulator2**: fit `DRAMModel.eta_seq`, `eta_mix` and `prio_leak` from micro-benchmarks:
  1. a single sequential stream, sweeping request size;
  2. two interleaved streams, sweeping the mix ratio;
  3. a read/write mix;
  4. the controller with and without priority.

  Then validate by replaying address traces of real segments (VLM alone, DiT alone, overlap, k=2), and report the error.

## Checks (`python3 tests_check.py`)

These run with ideal DRAM. All pass:
- serial S == L
- k=2 DiT weight traffic is W_D/2 per request
- k=2 S and L match the closed form, S = max(F_V/P, (W_V+W_D/2)/BW) and L ≈ T_V + 2S, when the VLM stream has priority
- the unbatched split gives no traffic saving

The fair policy gives S about 10% higher than the closed form. Under fair sharing the VLM is throttled while the DiT is active, so the bandwidth policy is itself a design knob.

## Known limitations / TODO

- No global-barrier mode (to be imported from the existing simulator if needed).
- No EdgeVLA-style dynamic core assist.
- Priority is strict: a weighted-share policy is still to be added.
- Uniform DiT weight residency fraction.
- Layer-granularity ops: fine for ms-scale L/S, not for burst-level jitter (use Ramulator replay for that).
- No input variability yet (prefix-length distribution, DRAM refresh noise), so L/S jitter is zero.

## On-chip memory (two levels)

- **Private, per core** (`local_kb`): holds double-buffered weight tiles, the activation tile and FP32 accumulators. At least about 128 KB is needed for 128×128 bf16. This is only a feasibility check plus area here. Its effect on op time should come from NeuSim through `compute_time_fn`.
- **Shared** (`sram_mb`): filled in priority order:
  1. DiT weight residency (optional);
  2. the VLM inter-layer activation working set (about 16 MB);
  3. prefix KV (about 18 MB per in-flight request).

  Whatever does not fit spills to DRAM and is counted as traffic: activations are written and read back once per layer, and KV is read by the DiT at every step.

## Parallel workflow: calibration and DSE run at the same time

DRAM parameters live in versioned files `calib/dram_vN.json`, each holding a nominal point and an interval.

| Track A: DRAM calibration (slow) | Track B: DSE (fast, never waits) |
|---|---|
| `ramulator_bridge/gen_traces.py micro`: write the micro-benchmark traces, then run them in Ramulator2. Start with the `seq_*` traces (η_seq has the largest effect) | `robustness.py calib/<current>.json`: sweep over the current interval. It reports which mapping decisions are already stable and which DRAM parameter moves S the most |
| `ramulator_bridge/fit_dram.py results.csv <prev>.json <next>.json`: fit whatever results are finished so far. The interval narrows and the version goes up | Re-run `robustness.py` / `run_sweep.py <next>.json` (minutes). Decisions that stay stable are final. For the rest, look at which parameter they depend on and calibrate that one next |
| `gen_traces.py segment`: generate held-out segment replays for shortlisted designs | Compare Ramulator's time and bandwidth for the same window against the model's prediction, and report the error |

`Simulator.run(record=True)` returns the per-op timeline that segment replay uses.

First quick look (prior interval, reduced space, placeholder model):
- median S spread across the interval is about 5%, but about 44% at p90 (bandwidth-bound designs);
- the best mapping is the same for half of the hardware configs;
- η_seq is the most influential parameter.
