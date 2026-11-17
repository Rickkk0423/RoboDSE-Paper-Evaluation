# Phase 3: Conditional Model And Issue Order

Date: 2026-11-15. The native backend remains the pinned eight-channel HBM2 setup
from Phase 2. No v2 calibration values or DSE rankings were changed. These are
simulator microbenchmarks, not independent VLA workload validation.

## Conditional Lookup Experiment

The predeclared design in `PHASE3_PLAN.md` contains 62 cases. Training uses
24 cases: 1/4 MiB, ratios 25/50/75%, at shifts 0/512/4096/65536 bytes. For each
shift and ratio, fit the median measured bandwidth; interpolate linearly between
ratios only. Never interpolate layouts or extrapolate ratio. The 38 other cases
are excluded from fitting; ten deliberately unsupported-layout cases require
abstention. The manifest and 10% threshold were fixed before native execution.

| Split | Cases | Conditional mean absolute error | Conditional max error | Frozen v2 scalar mean absolute error | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| Training (not validation) | 24 | 0.857% | 1.839% | 31.102% | Fits training |
| Held-out size: 16 MiB | 12 | 1.357% | 2.719% | 30.745% | Pass |
| Held-out ratio: 40/60% | 16 | 20.321% | 27.034% | 41.727% | Failed |
| Unsupported layout: shift 64 B | 10 | Not predicted | Not predicted | 32.987% | Abstained |

The conditional model improves on the scalar baseline but does not pass the
held-out-ratio gate. It is deliberately **not integrated into DSE**. Success on
larger streams means the lookup transfers across the tested traffic sizes at
the same ratio/layout; it does not establish general ratio or layout transfer.
Some conditions were previously seen in Phase 2 diagnostics, so these are
held-out-from-fit cases, not a claim of entirely unseen research conditions.

## Backend Counter Diagnostics

All 62 cases' native row classifications reconcile exactly with read requests
and completion counts. Counters are post-execution diagnostics, never fit inputs
or features assumed to be available to the analytical simulator.

Selected 16 MiB cases:

| DiT base shift | VLM byte share | Native GB/s | Row conflict fraction | Mean read latency (cycles) |
| --- | ---: | ---: | ---: | ---: |
| 0 B | 25% | 149.80 | 1.850% | 70.22 |
| 0 B | 40% | 153.41 | 1.884% | 69.41 |
| 0 B | 50% | 89.61 | 2.856% | 107.35 |
| 0 B | 60% | 152.02 | 1.897% | 69.71 |
| 0 B | 75% | 149.18 | 1.849% | 70.09 |
| 4096 B | 40% | 153.38 | 1.886% | 69.40 |
| 4096 B | 50% | 121.39 | 1.624% | 83.20 |
| 4096 B | 60% | 154.23 | 1.905% | 69.17 |

At shift 0 the balanced case has higher conflict fraction and latency than the
unbalanced cases. But changing shift to 4096 reduces the balanced conflict
fraction below the neighboring ratios without bringing its bandwidth up to
their level. Thus row-conflict fraction alone is not established as a sufficient
predictor; queue/service and request order need explicit controls. The average
per-channel read queue remains approximately 31-32 entries in these saturated
cases. These associations are not a causal timing decomposition.

## Controlled Issue-Order Probe

After the held-out-ratio failure, a second diagnostic fixes 50:50 bytes, 4 MiB
total traffic and each stream's exact address sequence. It changes only how
many consecutive 64-byte requests from one stream are offered before switching
to the other stream. Native issue width, FIFO policy and queue limit do not
change. Burst 1 reproduces the original balanced trace exactly; a regression
test checks identical output and invariant address multisets for other bursts.

| Consecutive requests per stream | Shift 0 bandwidth (GB/s) | Shift 4096 bandwidth (GB/s) |
| --- | ---: | ---: |
| 1 | 89.780 | 121.790 |
| 2 | 91.683 | 121.843 |
| 4 | 91.396 | 122.694 |
| 8 | 94.055 | 122.703 |
| 16 | 95.344 | 122.703 |
| 64 | 96.832 | 122.694 |

Max/min spread is 7.855% at shift 0 and 0.750% at shift 4096. Thus offered
request order affects bandwidth even at fixed byte ratio and addresses, with
an effect depending on layout. The tested order changes do not recover the
approximately 150 GB/s seen for unbalanced ratios and cannot explain the entire
ratio effect. No universal burst correction is justified by these two layouts.
This follow-up is diagnostic, not a fresh validation of the conditional lookup.

## Execution And Evidence

Remote isolated project: `/scratch/renati/vlasim_dse_20261115_phase2` on `einst`.
Slurm job 2043776 failed before trace execution because the repository-relative
v2 calibration file had not been copied to the remote checkout. After copying
the unchanged versioned file, job **2043779 completed in 1m55s**, including
54 tests and all 62 native cases. Its failure and retry logs are retained.
Job **2043789 completed in 14s**, including 56 tests and 12 controlled issue-order
cases. Both successful Phase 3 experiment jobs have finished; 74 native cases
were executed in total.

Local native evidence is in ignored `results/einst/layout_phase3/`:
`experiment_manifest.json`, `layout_report.json`, `counter_report.json`,
individual native reports and YAML statistics. Original CSV traces are now in
local `traces_backup.tar.gz` after the Phase 4 scratch-quota incident. All 62
members were checked against native trace hashes before releasing remote trace
copies. Archive SHA-256:
`5043a5a6c402561e024d11749148cdf3fc26d686a7fd7e28f8ce85d4b836617f`.
Counter analysis records its own source, input-report and individual stats hashes.
The order-probe reports, statistics and pre-execution manifest are copied to
`results/einst/issue_order_phase3/`; its large trace CSVs remain remote.

The final local test suite has 56 passing tests; the five original closed-form
checks and Python compilation also pass. The suite covers split uniqueness,
held-out exclusion from fitting, interpolation, abstention, failed-gate semantics,
native counter accounting and invariant byte/address traffic in the order probe.

## Remaining Gate

Do not create a universal `dram_v3` from this lookup. DSE currently has no
independently specified address-layout or stream-order descriptors. A deployable
model must declare its supported domain, abstain outside it and pass new
held-out workload tests. Current findings concern saturated all-read sequential
stream pairs under a pinned global FIFO, not arbitrary bursts, writes, hardware
controllers or closed-loop robot task behavior.
