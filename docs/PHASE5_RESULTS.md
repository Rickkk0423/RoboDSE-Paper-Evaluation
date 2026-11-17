# Phase 5: Prospective Offered-State Predictor

Date: 2026-11-15. Native Slurm job **2043935** completed on `einstein`
in **1m03s**. This is a trace-level regression experiment, not a runtime
resource-state engine, a DSE calibration replacement or silicon validation.

## Frozen Protocol

The experiment uses all 42 non-legacy Phase 4 cases, 21 per starting-address
shift (0 and 4096 bytes). Separate ridge models predict log makespan bandwidth
with alpha=1.0 and training-only feature normalization. Features are ten signed
cumulative cursor-progress bins, switch fraction, log maximum/mean run,
log request count, signed stream ratio, log mean absolute progress and negative
progress fraction. No native outcome counters enter the features.

The manifest, fitted model and all 34 predictions were written before native
execution. Held-outs introduce ratios 48.5/49.8/49.95/50.05/50.2/51.5% at 8 MiB,
2 MiB balanced/near-balanced traces, skew epochs 4/64, random seeds 41/73,
blocked bursts 8/128 and unsupported shift 512. The supported-case gate is
absolute bandwidth error <=10% for **every** case, not only average error.
Unsupported layouts must abstain. No holdout outcomes were added to training.

Unlike the earlier primary trimmed bandwidth metric, this experiment explicitly
targets **whole-run makespan bandwidth**. Comparisons below use that same target
for the model and the per-layout training-only scalar baseline.

## Complete Results

| Held-out group | Cases | Mean absolute error | Maximum absolute error | Gate |
| --- | ---: | ---: | ---: | --- |
| New ratios | 12 | 1.509% | 2.563% | Pass |
| New random orders | 4 | 3.575% | 4.867% | Pass |
| New local skew | 4 | 2.307% | 4.141% | Pass |
| New size, 2 MiB | 6 | 5.543% | 16.105% | Failed |
| New blocked bursts | 4 | 15.093% | 21.716% | Failed |
| Unsupported layout | 4 | Not predicted | Not predicted | Abstained |

The same-test scalar baseline mean absolute errors are 11.044%, 7.658%,
6.591%, 27.324% and 23.659%, respectively. Improvement over that baseline
does not override the failed gate. Notable failures are blocked128/shift0
(+21.716%), blocked8/shift4096 (+18.768%), uniform50.05%/shift4096/2MiB
(-16.105%) and blocked128/shift4096 (+11.601%). Signs mean predicted/actual-1.

The full state-model gate therefore **does not pass**. The model was not
integrated into request-level DSE. Fitting another model to these outcomes
would require fresh held-outs; discarding the failed groups is not validation.
The current feature histogram also discards temporal order beyond summary
statistics and is not an online bank/queue-state simulation.

## Provenance And Storage

HBM2 8-channel, 256 GB/s peak, FRFCFS/Open, 32-byte native transactions,
FIFO issue width 8 and maximum 512 outstanding remain unchanged. Source,
bridge/memory-library and expanded configuration hashes match training.
All 34 runs reconcile accepted/completed transactions, per-stream counts and
logical bytes. All traces and frozen artifacts have been hash-verified locally.

- Reports, model, predictions, features and native JSON/YAML:
  `results/einst/state_phase5/`.
- Batch log: `results/einst/slurm-2043935.log`.
- Trace archive: `results/einst/state_phase5_traces.tar.gz`.
- Archive SHA-256:
  `46ba018e824d97c7191bbb40610571b678ad6853ded95fd1dd5677ec8b52c7ef`.
- Manifest SHA-256:
  `2a803231058906e4949fe1c5ed2de3df0626d64cb123bafd4cfc6319e2e5ed99`.
- Frozen model SHA-256:
  `1b6bc3079d43f8efa97ab0d7531643e882ec0d6de5133442179988877a1a489c`.
- Frozen predictions SHA-256:
  `838cd2f5816a94c522f26bd60d176eac6646ed79c2b2249a3097a7840b5d9c6f`.

Node-local execution reused the isolated backend/environment without modifying
the adjacent integration checkout. Archived Phase 4 traces are required to
reproduce the training inputs. See `NATIVE_WORKFLOW.md` for commands and
`WORK_COMPLETION.md` for the other completed tracks and remaining gates.
