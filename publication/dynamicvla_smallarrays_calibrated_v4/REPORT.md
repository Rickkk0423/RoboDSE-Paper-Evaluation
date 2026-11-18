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

Calibration scope: `dynamicvla` / `dynamicvla_native_ramulator`. The calibrated DynamicVLA run uses the independent calibration JSON recorded in the manifest. Peak-bandwidth points outside the native calibration geometry remain sensitivity points, not calibrated physical channels.

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
| 1 x 16x16 | 12.8 | 8 | serial | 710.59 | 710.62 | 0.512 | 55.3% |
| 1 x 16x16 | 25.6 | 8 | serial | 520.69 | 520.74 | 0.512 | 75.4% |
| 1 x 16x16 | 51.2 | 8 | serial | 490.37 | 490.39 | 0.512 | 80.1% |
| 2 x 16x16 | 12.8 | 8 | serial | 585.62 | 585.65 | 1.024 | 33.5% |
| 2 x 16x16 | 25.6 | 8 | serial | 355.30 | 355.34 | 1.024 | 55.3% |
| 2 x 16x16 | 51.2 | 8 | serial | 260.34 | 260.37 | 1.024 | 75.4% |
| 4 x 16x16 | 12.8 | 8 | serial | 551.54 | 551.54 | 2.048 | 17.8% |
| 4 x 16x16 | 25.6 | 8 | serial | 292.81 | 292.82 | 2.048 | 33.5% |
| 4 x 16x16 | 51.2 | 8 | serial | 177.65 | 177.67 | 2.048 | 55.3% |
| 1 x 32x32 | 12.8 | 8 | serial | 551.96 | 552.01 | 2.048 | 17.8% |
| 1 x 32x32 | 25.6 | 8 | serial | 293.23 | 293.24 | 2.048 | 33.5% |
| 1 x 32x32 | 51.2 | 8 | serial | 180.03 | 180.04 | 2.048 | 54.5% |
| 2 x 32x32 | 12.8 | 8 | serial | 545.21 | 545.24 | 4.096 | 9.0% |
| 2 x 32x32 | 25.6 | 8 | serial | 275.98 | 276.00 | 4.096 | 17.8% |
| 2 x 32x32 | 51.2 | 8 | serial | 146.62 | 146.65 | 4.096 | 33.5% |
| 4 x 32x32 | 12.8 | 8 | serial | 544.86 | 544.87 | 8.192 | 4.5% |
| 4 x 32x32 | 25.6 | 8 | serial | 272.60 | 272.62 | 8.192 | 9.0% |
| 4 x 32x32 | 51.2 | 8 | serial | 137.99 | 138.00 | 8.192 | 17.8% |
| 1 x 64x64 | 12.8 | 8 | serial | 545.74 | 545.76 | 8.192 | 4.5% |
| 1 x 64x64 | 25.6 | 8 | serial | 273.49 | 273.50 | 8.192 | 9.0% |
| 1 x 64x64 | 51.2 | 8 | serial | 138.88 | 138.89 | 8.192 | 17.7% |
| 2 x 64x64 | 12.8 | 8 | serial | 545.13 | 545.13 | 16.384 | 2.3% |
| 2 x 64x64 | 25.6 | 8 | serial | 272.87 | 272.88 | 16.384 | 4.5% |
| 2 x 64x64 | 51.2 | 8 | serial | 136.74 | 136.75 | 16.384 | 9.0% |
| 4 x 64x64 | 12.8 | 8 | serial | 544.82 | 544.87 | 32.768 | 1.1% |
| 4 x 64x64 | 25.6 | 8 | serial | 272.56 | 272.57 | 32.768 | 2.3% |
| 4 x 64x64 | 51.2 | 8 | serial | 136.44 | 136.44 | 32.768 | 4.5% |

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
| dynamicvla_native_ramulator | 160/80 | 4 x 64x64 | 51.2 | 32 | V3/k2/batch | 140.19 | 69.62 | 16384 |
| dynamicvla_native_ramulator | 200/100 | 4 x 32x32 | 51.2 | 32 | V3/k2/batch | 171.22 | 80.39 | 4096 |
| dynamicvla_native_ramulator | 240/120 | 4 x 32x32 | 51.2 | 4 | V3/k2/batch | 210.14 | 105.08 | 4096 |
| dynamicvla_native_ramulator | 300/160 | 2 x 32x32 | 51.2 | 4 | serial | 146.62 | 146.65 | 2048 |
| dynamicvla_native_ramulator | 300/240 | 1 x 32x32 | 51.2 | 4 | serial | 180.03 | 180.04 | 1024 |

## Limits and Next Step

1. This establishes that a smaller-array search is useful; it does not establish a final minimum-cost chip or measured task success.
2. Keep serial/no-batching/batching alternatives. Smaller arrays can make computation dominant and reduce or reverse the value of cross-chunk batching.
3. BF16 target arithmetic is assumed although the source model is mixed FP32/BF16. Convolution uses an analytical compute floor; normalization, softmax and other non-matmul work are omitted. Small-array conclusions need convolution/tiling validation in particular.
4. SRAM working sets and traffic are approximate. The change from 512 KB to 32 KB private SRAM is checked only for static tile fit, not compiled buffering/tiling or runtime performance.
5. The native calibration itself uses the pinned HBM2 eight-channel Ramulator geometry; the 12.8/25.6/51.2 GB/s sweep is still a peak-bandwidth sensitivity study unless separately calibrated. Validate DiT batching numerically before robotic SR rollouts. Preserve the 40 ms control-step protocol and report any timing quantization explicitly.
6. Use timing boxes to shortlist designs; do not treat a longer permitted L as a success-rate guarantee. No imported SR surface was queried in this sweep.

## Reproduce

```sh
.venv/bin/python scripts/run_dynamicvla_smallarrays.py --calibration results/dynamicvla_calibration_20261118/dynamicvla_hbm2_8ch_v1.json --out results/dynamicvla_smallarrays_reproduction
.venv/bin/python scripts/report_dynamicvla_smallarrays.py --root results/dynamicvla_smallarrays_reproduction --out publication/dynamicvla_smallarrays_reproduction
```

Raw arrays remain in the corresponding `results/` directory. Previous pilot/V7/V9 files were not edited.
