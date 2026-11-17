# Phase 4: Temporal Progress Matters

Date: 2026-11-15. Slurm job **2043892** completed in **1m03s** on `einstein`
(`einst`), including 69 tests and 48 native runs. The design in `PHASE4_PLAN.md`
was fixed before execution. There is no new fitted model, calibration version
or change to the DSE ranking. These are saturated all-read microbenchmarks,
not silicon or independent end-to-end VLA measurements.

## Main Finding

Global byte ratio and fixed starting addresses do not uniquely determine
bandwidth in this backend. At a fixed global 50:50 ratio and identical per-stream
address sequences, changing only the offered stream order changes bandwidth
by 68.52% max/min at shift 0, and 39.24% at shift 4096. A static lookup over
ratio and starting phase cannot capture this controlled variation.

## Dense Near-Balance Sweep

Selected results from the 26-case 4 MiB dense sweep and six 16 MiB transfer runs:

| VLM share (requested) | Shift 0, 4 MiB GB/s | Shift 0, 16 MiB GB/s | Shift 4096, 4 MiB GB/s | Shift 4096, 16 MiB GB/s |
| --- | ---: | ---: | ---: | ---: |
| 49.0% | 148.116 | Not run | 154.713 | Not run |
| 49.5% | 158.995 | Not run | 162.443 | Not run |
| 49.9% | 121.639 | 154.026 | 136.211 | 160.728 |
| 50.0% | 89.780 | 89.606 | 121.790 | 121.395 |
| 50.1% | 118.629 | 153.615 | 102.672 | 141.234 |
| 50.5% | 159.327 | Not run | 148.707 | Not run |
| 51.0% | 147.901 | Not run | 153.707 | Not run |

Ratios are quantized to whole 64-byte requests; actual fractions are in the
offered descriptors. Peak physical bandwidth stays 256 GB/s. The primary metric
is the central 10%-90% completion bandwidth, not full-run throughput. Both are
retained: for example, the 49.9%/shift-0 case is 121.639 trimmed versus 118.136
makespan GB/s at 4 MiB, and 154.026 versus 147.968 GB/s at 16 MiB.

The dip is not limited to the exact 50:50 point at 4 MiB. At 16 MiB, 49.9% and
50.1% largely escape the shift-0 dip, while exact equality remains slow. Under
the uniform schedule, unequal stream counts create cumulative cursor drift;
exact balance keeps progress within one logical line. This is consistent with
relative-progress/layout interaction, not a proof of a particular bank-level
mechanism or a size-independent discontinuity.

For 49.9%, maximum absolute cursor skew grows from 8,512 B at 4 MiB to
33,728 B at 16 MiB; the fraction of offered prefixes within 4 KiB skew falls
from 0.481 to 0.121. For exact balance, maximum skew stays 64 B and that fraction
stays one. At shift 4096, the 49.9% and 50.1% directions are also asymmetric:
136.211 versus 102.672 GB/s at 4 MiB. Thus an absolute-skew-only correction
has not been justified; direction and phase need separate treatment.

## Fixed Global Ratio, Different Temporal Order

Every row below moves 2 MiB per stream, uses the same starting addresses and
preserves each stream's contiguous address sequence. Only label order changes.
Uniform integer interleaving is the original alternating balanced control.
Skew patterns pair a locally 40:60 window with its complementary window,
repeating the pair over the requested number of epochs. Shuffle cases use a
fixed local PRNG and preserve exact counts. The FIFO issue policy is unchanged.

| Pattern | Shift 0 GB/s | Shift 4096 GB/s |
| --- | ---: | ---: |
| Uniform balanced | 89.780 | 121.790 |
| Skew, 1 epoch | 151.295 | 152.547 |
| Skew, 16 epochs | 136.372 | 158.036 |
| Skew, 256 epochs | 90.180 | 134.669 |
| Shuffle, seed 17 | 128.423 | 113.501 |
| Shuffle, seed 29 | 117.780 | 115.438 |

Long skew windows recover much of the unbalanced capacity even though the
global ratio is exactly 50:50. Many short skew windows can remain close to the
balanced control. Random interleaving is neither universally faster nor a
layout-independent correction: at shift 4096 both random controls are slower
than the alternating control. Two seeds are order contrasts, not statistical
confidence estimates or a stochastic workload distribution.

## Generator And Accounting Controls

Six native runs compare the unchanged legacy floating-accumulator generator
against exact integer scheduling at 49/50/51% and both shifts. **All six trace
hashes match exactly and bandwidth differences are zero.** Therefore those
controls exclude a floating-generator artifact at the tested conditions; they
do not prove arbitrary future generators equivalent.

All runs reconcile accepted/completed counts, both streams' transaction counts
and native read row classifications. Offered descriptors were written before
native execution; row/queue counters are post-execution diagnostics only.
The final suite has 69 passing tests, including exact integer prefix counts,
fixed address-sequence preservation, local seeded RNG behavior and unique
experiment identities. The existing five closed-form checks still pass.

## Execution And Storage

Shared `/scratch` rejected source uploads with `Disk quota exceeded` before
submission. Only the previous experiment's generated trace copies were released,
after all 62 had been archived locally and checked against their native hashes.
The mount still rejected writes, so the new run used a private node-local tree:
`/tmp/vlasim_phase4_20261115.Os3Bob`. The original isolated Python environment
and native backend were reused via symlinks, not rebuilt or modified.

Native source manifest, bridge/memory-library hashes, expanded configuration,
issue width and outstanding limit match Phase 3. No unrelated projects were
cleaned or changed. Node-local results are not durable evidence by themselves:
reports, metadata, statistics, Slurm log and raw-trace archive have been copied
to ignored local `results/einst/balance_phase4/`. All 48 archived traces were
verified against native trace hashes, and their descriptors and exact per-stream
addresses were independently recomputed from the archived CSV content.
Manifest, source and per-case stats hashes were also checked. The raw archive
`traces_backup.tar.gz` SHA-256 is
`62c16299c023fccf62f7f1399bcb1e379b438f05e85f042070d614f7c6b07c3f`.

## Consequence For DSE

Do not replace v2 with a global-ratio or exact-equality special case. The next
model should track at least signed per-stream progress, layout phase and local
offered sequence/window behavior, with explicit support boundaries. These inputs
must come from workload/trace descriptions, not native outcome counters.

A prospective state-aware model and fresh held-out schedules are the next gate.
Until that passes, keep v2 as the previously documented conservative interval
reference and keep architecture recommendations conditional. Shape-level NeuSim
compute, real RW bursts, calibrated cost and task-success validation remain open.
