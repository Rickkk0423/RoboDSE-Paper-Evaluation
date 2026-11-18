# DynamicVLA extension snapshot

This branch preserves the DynamicVLA extension separately from the frozen
Pi0.5 V7/V9 delivery. It does not replace the Pi0.5 results.

## Contents

- `publication/dynamicvla_pilot/`: fixed-input checkpoint trace, modeled
  batching controls, reports, and compact verification evidence.
- `publication/dynamicvla_smallarrays/`: original small-array exploration.
- `publication/dynamicvla_calibration/`: native HBM2 eight-channel simulator
  measurements, fit, trace manifest, and backend metadata.
- `publication/dynamicvla_smallarrays_calibrated_v4/`: latest transferred-fit
  small-array sensitivity snapshot. The v2/v3 directories are historical
  snapshots, not additional independent experiments.
- `scripts/*dynamicvla*.py`, `tests/test_dynamicvla*.py`, and the workload
  and model-registry modules: profiling, simulation, reporting, and tests.

## Evidence boundaries

The native memory geometry has 256 GB/s peak bandwidth. Transferring its fit
to 12.8/25.6/51.2 GB/s does not calibrate those physical memory configurations.
The `dynamicvla_native_ramulator` label in generated sweep tables must not be
interpreted as independent calibration of each row. The latest generated
report also has incomplete controlled-example sections; empty sections do not
establish the absence of batching benefits.

The bounded synthetic trace generation and fit require further validation
before paper-level timing claims. Scheduler checks establish internal
consistency, not physical accuracy. GPU trace-repeat agreement does not
validate cross-chunk batching numerical equivalence. No new robotic success
rate rollouts are included.

Large generated traces, raw result arrays, native binaries, environments,
and caches remain excluded by the existing ignore rules. This branch is a
source and compact-results snapshot, not a full raw-evidence archive.
