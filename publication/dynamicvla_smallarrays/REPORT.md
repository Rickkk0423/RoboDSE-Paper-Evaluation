# DynamicVLA Resource-First Small-Array Sweep

Date: 2026-11-18. Exploratory modeled hardware timing only. No new GPU inference, Ramulator invocation or robot rollout was run. The successful fixed-input DynamicVLA trace from the previous pilot is reused unchanged.

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

51.2 GB/s is the inherited LPDDR5 fit anchor. 25.6 and 12.8 GB/s are hypothetical peak-bandwidth sensitivities using the same eta parameters. They are not new calibrated LPDDR configurations. Even the anchor fit was obtained with earlier traces, not DynamicVLA-specific calibration.

## Completed Work

- 81 hardware identities; 621 execution configurations; 3098 retained timing points.
- All serial and valid VLM/DiT splits, k=1, k=2/3 with and without batching.
- Minimum stable periods searched with 480 requests/96 warmup, followed by 621 configuration-level 960-request/192-warmup checks (594 unique semantics).
- Maximum 480/960 relative difference: 2.256e-10.
- 18 Python/C++ comparisons cover every array size and execution organization; maximum absolute difference 4.441e-16.
- Raw evidence and source hashes checked. These checks establish internal consistency, not physical timing accuracy.

## Fewer MAC Units, Useful Latency Range

Serial operation, 8 MB shared SRAM and 51.2 GB/s:

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | Peak TFLOP/s | Useful throughput / peak |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 x 16x16 | 51.2 | 8 | serial | 488.37 | 488.39 | 0.512 | 80.4% |
| 2 x 16x16 | 51.2 | 8 | serial | 245.40 | 245.41 | 1.024 | 80.0% |
| 4 x 16x16 | 51.2 | 8 | serial | 133.88 | 133.92 | 2.048 | 73.3% |
| 1 x 32x32 | 51.2 | 8 | serial | 138.08 | 138.10 | 2.048 | 71.1% |
| 2 x 32x32 | 51.2 | 8 | serial | 94.23 | 94.29 | 4.096 | 52.1% |
| 4 x 32x32 | 51.2 | 8 | serial | 78.66 | 78.67 | 8.192 | 31.2% |
| 1 x 64x64 | 51.2 | 8 | serial | 79.65 | 79.71 | 8.192 | 30.8% |
| 2 x 64x64 | 51.2 | 8 | serial | 75.21 | 75.27 | 16.384 | 16.3% |
| 4 x 64x64 | 51.2 | 8 | serial | 74.38 | 74.43 | 32.768 | 8.2% |

The last column is modeled useful FLOP/request divided by S and peak FLOP/s. It is not a measured array occupancy, active-cycle fraction or energy efficiency. Missing non-matmul costs and analytical convolution timing limit its accuracy.

## When Batching Does Not Help

Fixed two 32x32 cores, 8 MB SRAM, 51.2 GB/s; pipelined rows use one core per group:

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms |
| --- | --- | --- | --- | --- | --- |
| 2 x 32x32 | 51.2 | 8 | serial | 94.23 | 94.29 |
| 2 x 32x32 | 51.2 | 8 | V1/k1/batch | 166.10 | 135.00 |
| 2 x 32x32 | 51.2 | 8 | V1/k2/no-batch | 301.10 | 135.00 |
| 2 x 32x32 | 51.2 | 8 | V1/k2/batch | 259.49 | 129.76 |
| 2 x 32x32 | 51.2 | 8 | V1/k3/no-batch | 436.11 | 135.00 |
| 2 x 32x32 | 51.2 | 8 | V1/k3/batch | 378.69 | 120.18 |

With tiny compute groups, prefix execution can dominate. A hard VLM/DiT split then leaves insufficient prefix compute; sharing DiT weights does not remove that bottleneck. Serial remains in the full search and can win. A one-core time-multiplexed batching implementation is not represented by the current scheduler.

## Matched-Hardware Batching Examples

Examples below are selected within modeled L=100-300 ms and require a refresh reduction greater than 10% versus the same-hardware minimum-period serial point. Selection prioritizes fewer MAC units, then smaller SRAM. They are diagnostics, not unbiased aggregate task gains.

### inherited_fit_anchor

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | DiT GB/req |
| --- | --- | --- | --- | --- | --- | --- |
| 4 x 32x32 | 51.2 | 4 | serial | 78.66 | 78.67 | 1.980 |
| 4 x 32x32 | 51.2 | 4 | V3/k1/batch | 84.43 | 84.43 | 1.996 |
| 4 x 32x32 | 51.2 | 4 | V3/k2/no-batch | 168.86 | 84.43 | 1.996 |
| 4 x 32x32 | 51.2 | 4 | V3/k2/batch | 152.16 | 76.08 | 1.006 |
| 4 x 32x32 | 51.2 | 4 | V3/k3/no-batch | 253.29 | 84.43 | 1.996 |
| 4 x 32x32 | 51.2 | 4 | V3/k3/batch | 202.64 | 67.55 | 0.808 |
### uncalibrated_peak_sensitivity

| Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | DiT GB/req |
| --- | --- | --- | --- | --- | --- | --- |
| 4 x 32x32 | 25.6 | 4 | serial | 149.53 | 149.56 | 1.980 |
| 4 x 32x32 | 25.6 | 4 | V3/k1/batch | 153.08 | 153.10 | 1.996 |
| 4 x 32x32 | 25.6 | 4 | V3/k2/no-batch | 306.18 | 153.10 | 1.996 |
| 4 x 32x32 | 25.6 | 4 | V3/k2/batch | 226.71 | 113.38 | 1.006 |
| 4 x 32x32 | 25.6 | 4 | V3/k3/no-batch | 459.28 | 153.10 | 1.996 |
| 4 x 32x32 | 25.6 | 4 | V3/k3/batch | 316.43 | 105.49 | 0.808 |

## Resource-First Selection

The resource vector is (total MAC units, core count, shared SRAM, peak BW). Private SRAM is 32 KB per core throughout. Anchor and low-bandwidth sensitivity candidates are never mixed in one frontier. All timing-curve factors are considered, including points faster than 100 ms.

Below is one minimum-MAC witness per box, with ties broken by shared SRAM, BW, core count and then L. Full Pareto sets and witness identities are in `resource_frontiers.json`; these are not global area minima.

| Evidence scope | Box L/S ms | Hardware | BW GB/s | SRAM MB | Mapping | L ms | S ms | Total MACs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| inherited_fit_anchor | 160/80 | 1 x 64x64 | 51.2 | 4 | serial | 79.65 | 79.71 | 4096 |
| inherited_fit_anchor | 200/100 | 2 x 32x32 | 51.2 | 4 | serial | 94.23 | 94.29 | 2048 |
| inherited_fit_anchor | 240/120 | 2 x 32x32 | 51.2 | 4 | serial | 94.23 | 94.29 | 2048 |
| inherited_fit_anchor | 300/160 | 1 x 32x32 | 51.2 | 4 | serial | 138.08 | 138.10 | 1024 |
| inherited_fit_anchor | 300/240 | 1 x 32x32 | 51.2 | 4 | serial | 138.08 | 138.10 | 1024 |
| uncalibrated_peak_sensitivity | 160/80 | 4 x 64x64 | 25.6 | 32 | V3/k2/batch | 151.68 | 75.77 | 16384 |
| uncalibrated_peak_sensitivity | 200/100 | 4 x 32x32 | 25.6 | 32 | V3/k2/batch | 187.16 | 96.77 | 4096 |
| uncalibrated_peak_sensitivity | 240/120 | 4 x 32x32 | 25.6 | 4 | V3/k2/batch | 226.71 | 113.38 | 4096 |
| uncalibrated_peak_sensitivity | 300/160 | 2 x 32x32 | 25.6 | 4 | serial | 157.33 | 157.34 | 2048 |
| uncalibrated_peak_sensitivity | 300/240 | 1 x 32x32 | 25.6 | 4 | serial | 188.46 | 188.52 | 1024 |

## Limits and Next Step

1. This establishes that a smaller-array search is useful; it does not establish a final minimum-cost chip or measured task success.
2. Keep serial/no-batching/batching alternatives. Smaller arrays can make computation dominant and reduce or reverse the value of cross-chunk batching.
3. BF16 target arithmetic is assumed although the source model is mixed FP32/BF16. Convolution uses an analytical compute floor; normalization, softmax and other non-matmul work are omitted. Small-array conclusions need convolution/tiling validation in particular.
4. SRAM working sets and traffic are approximate. The change from 512 KB to 32 KB private SRAM is checked only for static tile fit, not compiled buffering/tiling or runtime performance.
5. Independently calibrate low-bandwidth candidates and validate DiT batching numerically before robotic SR rollouts. Preserve the 40 ms control-step protocol and report any timing quantization explicitly.
6. Use timing boxes to shortlist designs; do not treat a longer permitted L as a success-rate guarantee. No imported SR surface was queried in this sweep.

## Reproduce

```sh
.venv/bin/python scripts/run_dynamicvla_smallarrays.py --out results/dynamicvla_smallarrays_reproduction
.venv/bin/python scripts/report_dynamicvla_smallarrays.py --root results/dynamicvla_smallarrays_reproduction --out publication/dynamicvla_smallarrays_reproduction
```

Raw arrays remain in `results/dynamicvla_smallarrays_20261118/sweep/`. Previous pilot/V7/V9 files were not edited.
