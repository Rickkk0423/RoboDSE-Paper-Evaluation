# Phase 2: Native Calibration And Matched DSE

Experiment date: 2026-11-15. Execution used SSH alias `einst`, Slurm node
`einstein`, partition `dev`, in the isolated directory
`/scratch/renati/vlasim_dse_20261115_phase2`. Existing projects were not modified.
This is native Ramulator simulator calibration, not silicon measurement or
independent end-to-end VLA/NeuSim validation.

## Execution And Provenance

| Slurm job | Outcome | Work |
| --- | --- | --- |
| 2043575 | Failed | Build/tests completed; Linux shared-library loading failed |
| 2043595 | Completed | Fixed library preload; 24 native calibration cases and v1 campaign |
| 2043635 | Completed | Matched prior sweep and explicit v1 overlap coverage |
| 2043685 | Completed | Balanced-reference v2 fit, sweep, coverage and held-out capacity |
| 2043722 | Completed | 46 unit tests and address-phase probe |

All experiment jobs have settled. Remote `slurm-JOBID.log` files retain logs.
Source snapshots record per-file hashes; result metadata includes native bridge,
memory library, expanded configuration and trace hashes. Eight 4 MiB benchmark
cases also matched exactly between macOS and Linux on cycles, accepted/completed
transactions, bytes and both bandwidth metrics.

## Calibration

The pinned device is eight-channel HBM2 (`HBM2_2Gb`, `HBM2_2000Mbps`), with
256 GB/s physical peak, FRFCFS/Open controller and per-bank refresh. Trace issue
uses a global in-file FIFO, width 8 and at most 512 outstanding transactions.
Each logical 64-byte request is split into two 32-byte native transactions.
Throughput uses the central 10%-90% completion interval; makespan is also retained.

The 24 cases cover 1/4/16 MiB traffic sizes, each with three sequential tile
sizes, three mixed ratios and two RW diagnostics. Nine isolated and nine mixed
measurements enter the fit; RW diagnostics do not fit an explicit write penalty.
Strict priority is unsupported, so its prior remains unmeasured and priority
mappings are excluded from this DSE.

| Parameter | V2 nominal | Empirical interval |
| --- | ---: | --- |
| eta_seq | 0.5263309139 | 0.4757450832-0.5836179911 |
| eta_mix | 0.6650287744 | 0.5781421203-1.3062520837 |
| prio_leak (unmeasured) | 0 | 0-0.2 |

Nominal isolated bandwidth is 134.7407 GB/s and balanced mixed bandwidth is
89.6065 GB/s. The mixed envelope is 70.4124-195.1622 GB/s. Intervals are padded
empirical ranges, not confidence intervals. Mixed factors may exceed one because
interleaved address streams can improve locality/parallelism relative to the
isolated reference; effective bandwidth remains capped at physical peak.

V1 used an all-ratio nominal median (`eta_mix=1.1046635184`), which hid the
balanced case and failed overlap replay. V2 uses the balanced `mix_50` median
for the nominal reference while keeping all mixed observations in the bounds.
Both calibration versions are retained, with their status in `vlasim/calib/README.md`.

## Validation Gates

The first three shortlisted candidates were serial and therefore did not test
overlap. Explicit coverage now selects steady isolated windows and verifies
both streams reach the native backend for fully batched overlap k=1/2/3.
A scheduler annotation bug for partial k=3 rounds was corrected without changing
simulation timing; coverage uses actual request participants.

| Paced replay case | V1 completion-time error | V2 completion-time error |
| --- | ---: | ---: |
| Isolated VLM | 2.62% | 2.62% |
| Isolated DiT | 2.62% | 2.62% |
| Overlap k1 | 67.32% | 1.89% |
| Overlap k2 | 67.32% | 0.455% |
| Overlap k3 | 67.32% | 1.89% |

V2 passes the provisional 10% **paced replay** gate only. These all-read traces
uniformly distribute bytes over model-timed operations, so injection depends on
the model. They cannot establish independent end-to-end timing accuracy.

Independent, unpaced cases not used in fitting expose the remaining limitation:

| Held-out case | Native GB/s | Nominal GB/s | Prediction error | Inside interval |
| --- | ---: | ---: | ---: | --- |
| Sequential 256 KiB tile | 132.9144 | 134.7407 | +1.374% | Yes |
| Mix 40:60 | 154.7205 | 89.6065 | -42.085% | Yes |
| Mix 60:40 | 154.7419 | 89.6065 | -42.093% | Yes |

**Independent nominal capacity gate: FAILED. Tested interval gate: PASSED.**
Do not turn interval coverage into a universal accuracy claim.

At fixed 50:50 bytes, shifting only the DiT base address produced:

| Base shift (bytes) | Native GB/s |
| --- | ---: |
| 0 | 89.7796 |
| 64 | 91.7510 |
| 512 | 95.6888 |
| 4096 | 121.7896 |
| 65536 | 108.0896 |

Max/min is 1.35654, a 35.65% spread. Address layout matters under this pinned
mapper/controller/issue policy. This does not uniquely attribute every mix-ratio
difference to aliasing or establish behavior under other queue policies.

## Matched DSE

Prior, v1 and v2 each scan the same 60 mappings/hardware configurations at
33 DRAM points (1,980 rows per version), with 30 requests and provisional
mean L <= 250 ms. Hardware uses 1/2/3/4/6/8 cores, 32 MB shared SRAM,
2048 KB local SRAM/core and only fluid fair sharing.

| Cores | Prior robust mapping | Prior worst S (ms) | V2 robust mapping | V2 worst S (ms) |
| --- | --- | ---: | --- | ---: |
| 1 | Serial | 200.525 | Serial | 217.378 |
| 2 | Serial | 118.139 | Serial | 134.992 |
| 3 | Pipeline VLM2 k2 | 82.517 | Serial | 107.530 |
| 4 | Pipeline VLM3 k3 | 62.477 | Serial | 94.853 |
| 6 | Pipeline VLM5 k3 | 52.385 | Serial | 91.866 |
| 8 | Pipeline VLM7 k3 | 49.030 | Serial | 91.866 |

V2 nominal also selects serial at all six hardware points. This is a conditional
result of the present mixed envelope, not a final recommendation to serialize.
V2 mean endpoint sensitivity in S is -14.5862 ms for eta_seq and -30.9080 ms
for eta_mix; priority has zero effect because only fair mappings are tested.
Mixed behavior is the dominant measured uncertainty here.

Tie-aware reanalysis uses relative tolerance 1e-6 and intersection of near-optimal
mapping sets across points: prior has five stable hardware points and one
mapping-changing point; v1 and v2 each have two stable and four mapping-changing
points. These labels describe optimal sets across sampled points, not the robust
shortlist alone. Raw remote exact-winner reports are preserved; local reanalysis
records tolerance and analysis source hash. Stability is not a continuous proof.

## Evidence And Next Gates

Local copies are under ignored `results/einst/`:

- `phase2/`: v1 campaign, size-specific native outputs and initial candidates.
- `coverage_v1/coverage_report.json`: actual overlap failure.
- `matched_prior/`: matched prior raw sweep.
- `v2/`: nominal/robust outputs, `coverage/coverage_report.json` and
  `capacity/capacity_report.json`.
- `aliasing/aliasing_report.json`: fixed-ratio address-phase probe.
- `analysis/{prior,v1,v2}/`: tie-aware reports, summaries and shortlists.

Repository source artifacts include the batch scripts, backend snapshot
builder, runner, coverage/capacity/address probes and versioned calibration JSON.
Generated native builds and bulk results remain ignored; they are not assumed to
be available from a source-only checkout. The remote raw result tree is retained.

The next modeling gate is layout/row-conflict/queue-aware mixed behavior or
explicit conditional calibration, with new held-out cases. Compute still needs
explicit GEMM/vector shapes before NeuSim integration; checkpoint dimensions,
real RW bursts, independent schedules, area/energy and task success remain
unvalidated. Full online DSE and final task-aware hardware ranking are not claimed.
