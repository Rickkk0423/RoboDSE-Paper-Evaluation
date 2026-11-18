# DynamicVLA Calibration and DSE Extension

This delivery extends the existing Pi0.5 RoboDSE flow without changing frozen
Pi0.5/V7/V9 evidence.

## Evidence chain

1. `publication/dynamicvla_pilot/profile.json` is a real DynamicVLA GPU trace
   from checkpoint `e3da8b1e...`, with 569 prefix operations, 140 DiT
   operations per denoising step, 10 flow steps, and exact trace-repeat
   agreement.
2. `scripts/generate_dynamicvla_calibration.py` derives DynamicVLA-specific
   traffic sizes and bounded 64 MiB-per-stream Ramulator traces. It does not
   read or modify the Pi0.5 calibration.
3. The native bridge ran the DynamicVLA traces on the pinned HBM2 eight-channel
   Ramulator geometry. The resulting fit is `eta_seq=0.5268178553` and
   `eta_mix=0.6664201045`; priority behavior remains unmeasured.
4. `scripts/run_dynamicvla_smallarrays.py --calibration ...` consumes this
   model through the same periodic scheduler used by the earlier exploratory
   sweep. The no-argument path remains the original Pi0.5-anchor path.

## Scope

The calibration is simulator evidence for the recorded DynamicVLA traffic and
controller configuration, not a silicon measurement. The resulting 81-hardware
small-array sweep has 621 execution configurations, 594 unique 960-request
rechecks, and maximum 480/960 relative discrepancy `3.939e-10`. The 18
Python/C++ scheduler checks have maximum absolute error `4.441e-16`.

The calibrated sweep still uses 12.8, 25.6, and 51.2 GB/s as peak-bandwidth
parameters. Those points are not independently calibrated physical channels;
the native calibration geometry is HBM2 eight-channel at 256 GB/s peak.
Compute remains NeuSim GEMM timing plus an analytical convolution floor, and
non-matmul work and closed-loop task success are not modeled.

## Reproduce

```sh
.venv/bin/python scripts/generate_dynamicvla_calibration.py \
  --out results/dynamicvla_calibration_20261118/traces_v2

.venv/bin/python scripts/run_dynamicvla_smallarrays.py \
  --calibration results/dynamicvla_calibration_20261118/dynamicvla_hbm2_8ch_v1.json \
  --out results/dynamicvla_smallarrays_calibrated_20261118_v3

.venv/bin/python scripts/report_dynamicvla_smallarrays.py \
  --root results/dynamicvla_smallarrays_calibrated_20261118_v3 \
  --out publication/dynamicvla_smallarrays_calibrated_v3
```

The native measurement table, calibration JSON, trace manifest, and backend
metadata are retained under `publication/dynamicvla_calibration/`. Large raw
CSV traces remain local evidence under `results/` and are intentionally not
part of the source delivery.
