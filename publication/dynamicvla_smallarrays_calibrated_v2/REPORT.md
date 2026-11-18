# DynamicVLA Resource-First Small-Array Sweep

Date: 2026-11-18. Exploratory modeled hardware timing only. The successful fixed-input DynamicVLA trace from the previous pilot is reused unchanged. This delivery records the calibration scope in the manifest; it does not claim closed-loop task success.

## Search Objective

Seek smaller hardware meeting relaxed L/S upper bounds, not the lowest possible latency. We do not add artificial delay, lower the clock, or discard faster candidates just to force L into 100-300 ms. That range is an exploratory focus, not an empirically measured success contour.

All cores run at 1 GHz. The array choices are:

| Array per core | MAC units per core | Peak TFLOP/s per core | MAC units relative to 128x128 |
| --- | --- | --- | --- |
| 16x16 | 256 | 0.512 | 1/64 |
| 32x32 | 1024 | 2.048 | 1/16 |
| 64x64 | 4096 | 8.192 | 1/4 |
| 128x128 (previous pilot) | 16384 | 32.768 | 1 |

The sweep uses 1/2/4 cores, 4/8/32 MB shared SRAM, and 32 KB private SRAM per core. Private SRAM passes the existing static double-buffer tile feasibility test, but its capacity-dependent performance is NOT modeled. Reduction in MAC units or SRAM is not a measured die-area/power reduction.

Calibration scope: `pi05` / `unspecified`. The calibrated DynamicVLA run uses the independent calibration JSON recorded in the manifest. Peak-bandwidth points outside the native calibration geometry remain sensitivity points, not calibrated physical channels.

## Completed Work

- 81 hardware identities; 621 execution configurations; 3104 retained timing points.
- All serial and valid VLM/DiT splits, k=1, k=2/3 with and without batching.
- Minimum stable periods searched with 480 requests/96 warmup, followed by 621 configuration-level 960-request/192-warmup checks (594 unique semantics).
- Maximum 480/960 relative difference: 3.939e-10.
- 18 Python/C++ comparisons cover every array size and execution organization; maximum absolute difference 4.441e-16.
- Raw evidence and source hashes checked. These checks establish internal consistency, not physical timing accuracy.

## Fewer MAC Units, Useful Latency Range

Serial operation, 8 MB shared SRAM and 51.2 GB/s:

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | Peak TFLOP/s | Useful throughput / peak |
| --- | --- | --- | --- | --- | --- | --- | --- |

The last column is modeled useful FLOP/request divided by S and peak FLOP/s. It is not a measured array occupancy, active-cycle fraction or energy efficiency. Missing non-matmul costs and analytical convolution timing limit its accuracy.

## When Batching Does Not Help

Fixed two 32x32 cores, 8 MB SRAM, 51.2 GB/s; pipelined rows use one core per group:

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms |
| --- | --- | --- | --- | --- | --- |

With tiny compute groups, prefix execution can dominate. A hard VLM/DiT split then leaves insufficient prefix compute; sharing DiT weights does not remove that bottleneck. Serial remains in the full search and can win. A one-core time-multiplexed batching implementation is not represented by the current scheduler.

## Matched-Hardware Batching Examples

Examples below are selected within modeled L=100-300 ms and require a refresh reduction greater than 10% versus the same-hardware minimum-period serial point. Selection prioritizes fewer MAC units, then smaller SRAM. They are diagnostics, not unbiased aggregate task gains.

No qualifying example in this sweep.

## Resource-First Selection

The resource vector is (total MAC units, core count, shared SRAM, peak BW). Private SRAM is 32 KB per core throughout. Anchor and low-bandwidth sensitivity candidates are never mixed in one frontier. All timing-curve factors are considered, including points faster than 100 ms.

Below is one minimum-MAC witness per box, with ties broken by shared SRAM, BW, core count and then L. Full Pareto sets and witness identities are in `resource_frontiers.json`; these are not global area minima.

| Evidence scope | Box L/S ms | Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | Total MACs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Limits and Next Step

1. This establishes that a smaller-array search is useful; it does not establish a final minimum-cost chip or measured task success.
2. Keep serial/no-batching/batching alternatives. Smaller arrays can make computation dominant and reduce or reverse the value of cross-chunk batching.
3. BF16 target arithmetic is assumed although the source model is mixed FP32/BF16. Convolution uses an analytical compute floor; normalization, softmax and other non-matmul work are omitted. Small-array conclusions need convolution/tiling validation in particular.
4. SRAM working sets and traffic are approximate. The change from 512 KB to 32 KB private SRAM is checked only for static tile fit, not compiled buffering/tiling or runtime performance.
5. Independently calibrate low-bandwidth candidates and validate DiT batching numerically before robotic SR rollouts. Preserve the 40 ms control-step protocol and report any timing quantization explicitly.
6. Use timing boxes to shortlist designs; do not treat a longer permitted L as a success-rate guarantee. No imported SR surface was queried in this sweep.

## Reproduce

```sh
.venv/bin/python scripts/run_dynamicvla_smallarrays.py --calibration results/dynamicvla_calibration_20261118/dynamicvla_hbm2_8ch_v1.json --out results/dynamicvla_smallarrays_reproduction
.venv/bin/python scripts/report_dynamicvla_smallarrays.py --root results/dynamicvla_smallarrays_reproduction --out publication/dynamicvla_smallarrays_reproduction
```

Raw arrays remain in `results/dynamicvla_smallarrays_20261118/sweep/`. Previous pilot/V7/V9 files were not edited.
