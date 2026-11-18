# DynamicVLA Small-Core Pilot

Date: 2026-11-18. Status: exploratory hardware-model results, not paper-ready physical or task validation.

## What Actually Ran

- Dedicated Slurm GPU job 2069331 on blue-space, NVIDIA H20, submitted via einst.
- Loaded the real DOM checkpoint; checkpoint SHA-256: `e3da8b1e0326d7a3ee6873f7fa17cdf7015201251901be5107377cb851ce3af8`.
- 430,155,272 parameter elements; 1.118 GB runtime parameter storage, mixed FP32/BF16.
- Synthetic fixed input: two cameras, two observation frames, one short instruction; H=20; 10 denoising steps; prefix length 78.
- Two warmups, five timed requests, then one traced request. Output [1,20,7], finite; repeat/trace max absolute error both zero.
- Instrumented host inference mean 203.120 ms; prefix CUDA-event mean 39.301 ms; DiT mean 15.772 ms per step (157.722 ms for ten steps).
- These are GPU sanity timings for one input, not NPU timing validation, a representative task distribution, or a performance guarantee.
- No shared service modified; no robotic episodes; no real cross-chunk batching implementation executed.

The first GPU job (2069194) failed while saving due to Python 3.10 lacking hashlib.file_digest. Job 2069213 completed but omitted composite attention matmul events. Its trace was rejected for DSE. Job 2069331 includes these events and is the sole DSE input. The earlier dev-queue request 2069160 was cancelled while pending; no unrelated jobs were cancelled.

## Hardware Search

- Main sweep: cores 1/2/3/4/6/8; LPDDR5 51.2/102.4/204.8 GB/s; 32 MB shared SRAM; 512 KB private SRAM per core.
- Each core is a 128x128 array at 1 GHz. Core count is not interchangeable with GPU cores or SMs.
- All nonempty VLM/DiT splits; serial; pipeline k=1; k=2/3 with and without batching. One-core hardware supports only serial in this implementation.
- Supplemental 8 MB and 64 MB SRAM sweeps cover 1/2/3/4 cores at all three bandwidths.
- 492 configurations and 2460 retained timing points across 42 hardware identities.
- Search uses 480 requests and 96 warmup requests. Each configuration's minimum stable-period point has a 960-request/192-warmup consistency check. Other curve factors are not all rechecked at 960 requests.
- Maximum 480/960 relative timing difference: 1.954e-10.
- Six 24-request Python/C++ reference comparisons also passed. These are consistency checks, not independent physical calibration.

## Controlled Batching Result

51.2 GB/s, 4 cores, 32 MB SRAM. Every pipeline row fixes allocation at 2 VLM + 2 DiT cores. Serial uses all four cores for each phase. Traffic values are model estimates, not GPU DRAM counters.

| Organization | L (ms) | S (ms) | DiT GB/request | Total GB/request |
| --- | --- | --- | --- | --- |
| Serial (all 4 cores) | 57.191 | 57.214 | 1.980 | 2.800 |
| Pipeline k=1, batched | 58.179 | 58.186 | 1.996 | 2.818 |
| Pipeline k=2, unbatched | 116.365 | 58.186 | 1.996 | 2.818 |
| Pipeline k=2, batched | 76.448 | 38.243 | 1.006 | 1.828 |
| Pipeline k=3, unbatched | 174.551 | 58.186 | 1.996 | 2.818 |
| Pipeline k=3, batched | 102.627 | 34.207 | 0.808 | 1.630 |

Relative to the k=1 pipeline control, k=2 reduces S by 34.27%, DiT traffic by 49.60%, and total traffic by 35.13%. At k=3 these reductions are 41.21%, 59.52%, and 42.16%. Longer L is the tradeoff. The 10-step schedule splits unevenly at k=3 (4/3/3), so traffic does not fall to exactly one third.

## Does Fewer Cores Make Sense?

Serial refresh interval, 32 MB SRAM:

| Cores | 51.2 GB/s: S (ms) | 102.4 GB/s: S (ms) | 204.8 GB/s: S (ms) |
| --- | --- | --- | --- |
| 1 | 60.200 | 33.329 | 20.761 |
| 2 | 58.186 | 30.204 | 17.428 |
| 3 | 57.561 | 29.510 | 16.387 |
| 4 | 57.214 | 29.163 | 15.901 |
| 6 | 57.145 | 29.024 | 15.762 |
| 8 | 57.145 | 28.954 | 15.692 |

In this model, small-core designs merit priority: adding cores alone gives diminishing returns at fixed bandwidth. This does not mean the vision prefix is negligible: traced matrix/conv work is 159.432 GFLOP for the prefix and 41.633 GFLOP for ten DiT steps. Model parameter count alone is insufficient to size compute.

## SRAM Sensitivity

Same 51.2 GB/s, four cores and 2+2 split:

| Shared SRAM (MB) | k, batching enabled | L (ms) | S (ms) |
| --- | --- | --- | --- |
| 8.0 | 1 | 75.037 | 75.059 |
| 8.0 | 2 | 110.184 | 55.120 |
| 8.0 | 3 | 153.251 | 51.091 |
| 32 | 1 | 58.179 | 58.186 |
| 32 | 2 | 76.448 | 38.243 |
| 32 | 3 | 102.627 | 34.207 |
| 64.0 | 1 | 58.156 | 58.186 |
| 64.0 | 2 | 76.426 | 38.243 |
| 64.0 | 3 | 102.603 | 34.207 |

The trace-derived full-output activation working-set estimate is 28.312 MB. At 8 MB, modeled prefix spilling increases S: batching still helps, but the 32 MB result cannot be transferred unchanged to a smaller-SRAM chip. This estimate is not a tile-level allocation or compiler liveness analysis.

## Timing Boxes Are Not Success Contours

The supplemental `timing_box_frontiers.json` uses 40 ms-related timing boxes for hardware screening only:

| Box Lmax/Smax (ms) | Search arm | Pareto vectors (GB/s, cores) |
| --- | --- | --- |
| 40/40 | serial | [(102.4, 1)] |
| 40/40 | no_batching | [(102.4, 1)] |
| 40/40 | full | [(102.4, 1)] |
| 80/40 | serial | [(102.4, 1)] |
| 80/40 | no_batching | [(102.4, 1)] |
| 80/40 | full | [(51.2, 3), (102.4, 1)] |
| 120/40 | serial | [(102.4, 1)] |
| 120/40 | no_batching | [(102.4, 1)] |
| 120/40 | full | [(51.2, 2), (102.4, 1)] |
| 80/80 | serial | [(51.2, 1)] |
| 80/80 | no_batching | [(51.2, 1)] |
| 80/80 | full | [(51.2, 1)] |
| 120/80 | serial | [(51.2, 1)] |
| 120/80 | no_batching | [(51.2, 1)] |
| 120/80 | full | [(51.2, 1)] |

These frontiers compare bandwidth/core vectors only at fixed 32 MB SRAM. They are not area Pareto sets or matched-SR results. At 102.4 GB/s even one-core serial is below 40 ms in the model. The current robotic harness cannot demonstrate arbitrary extra refresh gains below its 40 ms control period. At 51.2 GB/s the serial/batched trajectories cross control-step-relevant ranges, making that bandwidth more informative for eventual validation. Rounded or quantized timings must be reported as a different protocol, not silently substituted for the original hardware point.

## Evidence Limits and Next Step

1. Target arithmetic is uniformly BF16, while the loaded checkpoint uses mixed precision. No numerical equivalence test of that conversion was performed.
2. Traced linear and attention GEMMs use the pinned NeuSim provider. Vision convolutions use an analytical compute estimate; normalization, softmax, elementwise work, biases and other movement are not fully modeled.
3. Memory uses the historical Ramulator-calibrated fluid model. No new Ramulator process was invoked for this pilot, and the fit has not been validated for DynamicVLA traces.
4. Traffic assumes streamed matrix weights, approximate prefix spills and uniform KV read/write placement. Cache reuse and tile-level activation liveness need a dedicated mapping/calibration pass.
5. The synthetic short prompt gives 78 prefix tokens. Longer instructions or other input protocols require new traces. Batching effects are modeled, not measured on the deployed policy.
6. Prioritize 1-4 cores and 8/32 MB SRAM, retain 6/8 cores as controls, calibrate representative DynamicVLA memory/vision workloads, and test mixed-timestep batched DiT output equivalence before claiming hardware or task gains. Defer SR rollouts until those timing assumptions are credible.

## Reproduce

From the project root, using the delivered profile:

```sh
.venv/bin/python scripts/run_dynamicvla_pilot.py --profile publication/dynamicvla_pilot/profile.json --out results/dynamicvla_reproduction
```

Use `--cores 1,2,3,4 --sram-mb 8` or `--sram-mb 64` with distinct output directories for supplemental sweeps. Raw search/recheck arrays and failed-probe logs remain under `results/dynamicvla_pilot_20261118/`; the compact publication directory contains tables, manifests, the successful trace and verification results. Frozen V7/V9 results were not modified.
