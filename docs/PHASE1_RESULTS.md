# Phase 1: Analytical DSE Baseline

Date: 2026-11-15. All numbers below are provisional model outputs, not measured
NeuSim/Ramulator results or final hardware recommendations.

## Completed

- Imported the supplied archive and recorded its checksum in the root README.
- Added a locked, isolated Python environment and portable command entry points.
- Fixed macOS multiprocessing entry safety, infeasible-as-stable counting,
  full mapping identity, compute-hook consistency in balance progress estimates,
  reusable simulator state and trace generation traffic/write-ratio errors.
- Added calibration input validation, uncertainty propagation for mixed efficiency,
  metadata retention, new-version output protection and trace manifests.
- Ran 29 regression tests plus all five original closed-form checks successfully.

## Experiment

Command: the root README's small-space sweep with `--points 3`, prior calibration
`v0-prior`, 30 requests, warmup 6 and simulator-defined pipeline drain exclusion.
There are 174 configurations across 12 hardware points. Each is evaluated at 33
parameter points (27 grid points plus additional nominal/nominal-axis points):
**5,742 evaluated rows**. All configurations pass the SRAM feasibility checks.

The budget is provisionally **mean L <= 250 ms**. It has not been inferred from
closed-loop task measurements, and is not a tail-latency constraint.

| Decision Status | Hardware Points |
| --- | ---: |
| Same optimal mapping at every sampled point | 6 |
| Optimal mapping changes | 5 |
| Budget feasibility changes | 1 |
| Infeasible at every sampled point | 0 |

The feasibility-changing hardware is 1 core / 100 GB/s. Mapping-changing hardware
is 3 cores / 100 or 200 GB/s and 4 cores / 100, 200 or 400 GB/s. Do not finalize
these deployment choices using nominal parameters alone.

The median S spread across the interval is **8.66%**; p90 is **47.22%**. Exact
nominal-axis mean-S changes from each parameter's lower to upper endpoint are:

| Parameter | Range | Mean S Change |
| --- | --- | ---: |
| eta_seq | 0.70 to 0.95 | -5.764 ms |
| eta_mix | 0.80 to 1.00 | -1.471 ms |
| prio_leak | 0.00 to 0.20 | +2.414 ms |

These are equally weighted averages across mappings, not causal task effects.
**Calibrate eta_seq first** within this model and search scope.

## Candidates

Eleven hardware points have a mapping satisfying the budget at every sampled
point. Each candidate minimizes worst sampled S for its hardware; this is distinct
from having an invariant pointwise-optimal mapping.

| Cores | GB/s | Organization | Worst L (ms) | Worst S (ms) |
| ---: | ---: | --- | ---: | ---: |
| 4 | 400 | pipeline, VLM=3, k=3, fair | 185.12 | 54.92 |
| 4 | 200 | pipeline, VLM=3, k=2, VLM priority | 211.46 | 71.40 |
| 3 | 400 | serial | 77.81 | 77.81 |
| 3 | 200 | pipeline, VLM=2, k=2, balance | 227.94 | 83.67 |

All use 32 MB shared SRAM and 2048 KB private SRAM/core. This is a throughput
ordering, not a cost/energy Pareto frontier. Nominal-parameter checks of all eleven
candidates at 30 and 120 requests change mean L/S by less than 1e-8 percent.
This convergence check does not cover every interval point or stochastic inputs.

## Evidence And Next Gates

Raw outputs are local, ignored experiment artifacts under `results/v0/`:
`nominal/`, `robust/`, `candidates/`, `micro/`, and `segments/`.
The initial robust scan finished simulation and CSV export but failed JSON export
on a NumPy boolean; the report was regenerated with `--from-csv` after the fix.
Its `n_requests` is null because that legacy CSV did not contain request counts;
the actual invocation used 30. Subsequent fresh sweeps record counts per row.

Micro smoke traces contain 1,024 requests each, eleven traces total. A default
segment-generation smoke produced 4,887,495 requests for the 600-602 ms window.
Neither was executed by Ramulator. Manifest hashes identify generated traffic.

Next: choose and pin the adjacent backend's DRAM organization, clock, controller,
address mapping and issue limits; adapt the trace frontend; collect saturated
isolated sequential measurements before fitting `dram_v1.json`. Then rerun DSE
and held-out overlap validation. Priority calibration requires actual controller
support and a controlled isolated-service reference, not just offered demand.

NeuSim integration additionally requires explicit GEMM/vector shapes: aggregate
layer FLOPs in the current `Op` are not a valid direct `gemm_ns` input. Checkpoint
shape verification, calibrated cost constants and task-aware selection remain open.
