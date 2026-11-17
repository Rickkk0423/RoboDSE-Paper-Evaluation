# Native Calibration Workflow

The native path executes the Ramulator C++ backend. It is simulator calibration,
not a silicon measurement. All experimental source/build directories and results
are isolated from the adjacent integration checkout.

## Local

```bash
uv sync --extra test --extra native --locked
uv run python vlasim/ramulator_bridge/build_backend.py ../Ramulator_parallel --out .native/backend
uv run python vlasim/ramulator_bridge/campaign.py --backend .native/backend --out results/phase2 --procs 4
```

`build_backend.py` snapshots native sources, the Python configuration exporter,
the Ramulator source and vendored dependencies, preserving LICENSE and NOTICE.
Per-file SHA-256 hashes are recorded before building. CMake uses vendored dependency
sources explicitly and generates an AppleClang compatibility header in the build
directory, leaving the original checkout unchanged. Reuse a completed backend by
passing its directory to the runner; new builds require a fresh output directory.

The campaign runs 1, 4 and 16 MiB per benchmark. Each size contains three isolated
sequential tile sizes, three mixed read-stream ratios and two RW diagnostics.
Fit inputs combine all sizes; empirical bounds retain size/locality variation
rather than treating it as random noise. Unsupported strict-priority traces are
rejected, not silently executed without priority.
The nominal mixed factor uses the median balanced `mix_50` bandwidth when present,
matching saturated fluid fair sharing. The uncertainty envelope still includes
all mixed ratios and propagates the isolated-efficiency range. An all-ratio median
was tried as v1 and failed overlap replay; v2 is a conditional balanced reference,
not a claim that every ratio/layout has the same efficiency.

The calibrated DSE uses `configs/dse_hbm2_8ch.json`: 1/2/3/4/6/8 NPU cores, 32 MB
shared SRAM, 2048 KB private SRAM/core, and the actual configured 256 GB/s peak.
Only the fluid fair policy is considered. FRFCFS is not a max-min-fair controller:
the fluid policy remains an approximation to be checked in held-out replay.
Calibration metadata prevents accidental sweeps over different peak bandwidths
or unsupported strict-priority mappings.

## Einstein

Use an isolated directory on `einst` (hostname/node `einstein`) and submit through
Slurm. The batch script requests the `dev` partition, 4 CPUs, 8 GB and 20 minutes.
It installs the locked Python dependencies inside the allocation, builds the
backend, runs unit/closed-form tests and executes the campaign.

```bash
ssh einst sbatch --parsable --chdir=/scratch/renati/vlasim_dse_20261115_phase2 /scratch/renati/vlasim_dse_20261115_phase2/scripts/einst_calibrate.sh
```

That directory contains project files plus `backend_source/`, a source-only copy
of the local snapshot, and `original_source_manifest.json` identifying its origin.
No existing remote project, virtual environment, running job or source tree is
modified. Do not run this submission twice in the same directory: outputs are
deliberately non-overwriting. Follow-up runs should use fresh result directories
and reuse the completed native build.

## Measurement Semantics

- Trace rows are `issue_time_ns,stream,R_or_W,address` with no header, sorted by time.
- Each 64-byte logical request becomes two 32-byte HBM2 native transactions.
- An explicit global FIFO preserves input order. A rejected head retries next
  cycle; up to eight transactions issue per cycle, with at most 512 outstanding.
  Thus queueing/head-of-line effects are part of this calibration's scope.
- Callback IDs are tracked from acceptance through completion. Unexpected,
  duplicated or missing completions fail the run. A cycle-budget timeout is not
  reported as successful throughput.
- The primary fit bandwidth uses the central 10%-90% completion interval, counting
  bytes between its endpoints. Whole-run makespan bandwidth is also retained.
- Write callbacks follow backend semantics (final write command issue); they do
  not imply write-recovery time has elapsed. RW results remain diagnostics because
  the analytical model does not yet have a distinct RW penalty parameter.
- Metadata records peak bandwidth, issue limits, exact expanded YAML hash, source
  manifest hash and both native bridge and memory-library hashes. On Linux the
  runner explicitly preloads the memory library with global symbol visibility to
  avoid the inherited RPATH layout issue. Individual results retain trace hashes,
  transaction counts, simulated cycles and callback latencies.

## Model Change Motivated By Evidence

The supplied model assumed `eta_mix <= 1`, i.e. interleaving could only hurt. Native
HBM2 microbenchmarks show some mixed address streams outperform the selected
isolated stream because locality and bank-level parallelism differ. `eta_mix` is
therefore a positive **relative factor**, potentially above one, while effective
bandwidth is always capped at physical peak. `eta_seq` remains in (0,1].

This change does not establish that one factor fits every locality or mix ratio.
Wide intervals or replay errors are evidence of model inadequacy, not a reason to
clip observations. Priority leak remains unmeasured and its prior is retained.

## Validation Gate

The first three robust candidates receive separate held-out paced segment replays.
`campaign_report.json` records completion-time error against the model window and
a provisional 10% gate. A failed gate prevents a validation claim, but the campaign
still completes successfully as an experiment capturing the disagreement.
Even passing only validates this paced replay: bytes are uniformly issued within
each op, all segment traffic is reads, and injection timing comes from the model.
This is not independent end-to-end VLA timing validation. Explicit kernel shapes,
NeuSim compute integration, real RW bursts and independent replay schedules remain
necessary before making final architecture claims.

Candidate selection can produce only serial windows, so it is not a coverage
test. Run explicit isolated VLM/DiT and fully batched overlap k=1/2/3 checks, then
independent unpaced capacity cases and a fixed-ratio address-phase probe:

```bash
uv run python vlasim/ramulator_bridge/validate_coverage.py vlasim/calib/dram_v2_hbm2_8ch.json --backend .native/backend --config configs/hbm2_8ch.json --out results/coverage
uv run python vlasim/ramulator_bridge/validate_capacity.py vlasim/calib/dram_v2_hbm2_8ch.json --backend .native/backend --config configs/hbm2_8ch.json --out results/capacity
uv run python vlasim/ramulator_bridge/probe_aliasing.py --backend .native/backend --config configs/hbm2_8ch.json --out results/aliasing
```

On Einstein, the corresponding follow-up scripts are `scripts/einst_coverage.sh`,
`scripts/einst_refit.sh` and `scripts/einst_aliasing.sh`. Inspect their output
paths before resubmission; result directories are intentionally non-overwriting.

The executed v2 results pass paced replay (0.455%-2.62% completion-time error),
but **fail independent nominal mixed-capacity prediction** (about -42% bandwidth
error for held-out 40:60 and 60:40 streams). The empirical interval covers these
cases. Shifting the second stream's base at fixed 50:50 mix changes bandwidth by
35.65% max/min. These gates require layout-aware modeling or conditional
calibration before point estimates can support final architecture ranking.
See `PHASE2_RESULTS.md` for evidence paths and job provenance.

## Temporal-Order Diagnostics

The Phase 3 conditional lookup and Phase 4 near-balance probes are separate
experiments, not replacement DSE calibrations. See `PHASE3_RESULTS.md` and
`PHASE4_RESULTS.md` for failed ratio interpolation and controlled order effects.
The latter can be reproduced with:

```bash
uv run python vlasim/ramulator_bridge/probe_balance.py --backend .native/backend --config configs/hbm2_8ch.json --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/balance_phase4
```

Use `scripts/einst_balance.sh` in a fresh isolated project directory. If shared
scratch is quota-limited, node-local storage may be used on the explicitly pinned
Slurm node, but copy reports and hash-verified raw traces to durable storage
before relying on the experiment. Do not clean unrelated project files to make
room. A phase-dependent runtime model needs a separate validation gate before
integration into the request-level simulator.

## Prospective State Model And Final Checks

Restore the hash-verified Phase 4 training traces before running the state model.
Use a fresh output directory; predictions are frozen before native execution:

```bash
uv sync --extra test --extra native --extra analysis --extra compute --locked
uv run python vlasim/ramulator_bridge/state_campaign.py --training results/balance_phase4 --backend .native/backend --config configs/hbm2_8ch.json --out results/state_phase5
uv run python vlasim/snapshot_compute.py ../Ramulator_parallel --out .native/compute
uv run python vlasim/compute_campaign.py --snapshot .native/compute --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/compute_checked_new
uv run python vlasim/interval_convergence.py results/einst/v2/robust/shortlist.csv vlasim/calib/dram_v2_hbm2_8ch.json --out results/convergence_new
uv run python vlasim/analysis/task_report.py vlasim/data/libero_dynamic_L_S.csv results/einst/v2/robust/shortlist.csv --samples results/einst/v2/robust/robust_LS.csv --out results/task_new
uv run python vlasim/audit_plan.py --state results/state_phase5/state_report.json --compute results/compute_checked_new/compute_report.json --convergence results/convergence_new/convergence_report.json --task results/task_new/task_report.json --out results/audit_new
```

Compute snapshots preserve source/license files and a per-file SHA-256 manifest;
the provider verifies contents and imported module provenance. Supply the adjacent
integration source only to the snapshot tool, never edit it for these experiments.
The compute campaign intentionally enables a clearly labeled analytical SigLIP
fallback after checking strict rejection. Unsliced hybrid results do not validate
the original sliced architecture sweep.

Einstein scripts: `einst_state.sh`, `einst_finish.sh`,
`einst_verify_compute.sh`. Inspect their fixed output paths and node-local setup
before submission. Final jobs 2043978/2043987 completed successfully; copied
Linux reports agree with local results to floating-point roundoff.
See `PHASE5_RESULTS.md` for the failed full state-model gate, and
`WORK_COMPLETION.md` for final evidence locations and unresolved scientific gates.

## Case v3 Prerequisites

`case_v3_p0.py` uses the optional per-channel nonblocking frontend without
modifying the fixed native backend. It adds LPDDR5 configuration export using
the pinned upstream standard/controller and preserves 32-byte transactions,
FRFCFS/Open and 512 outstanding. `case_v3_followup.py` isolates mapper and issue
width changes; `case_v3_audit.py` checks native accounting and emits explicitly
blocked main-case status rather than an invented sweep/frontier.

Einstein scripts are `einst_case_v3_p0.sh`, `einst_case_v3_followup.sh` and
`einst_case_v3_lpddr.sh`. Read `CASE_V3_RESULTS.md` before selecting a calibration:
LPDDR peak rates differ from the target names, high-bandwidth injection can be
frontend-limited, and old-mapper BG isolation does not validate MOP4CLXOR isolation
or a fixed channel-partition bandwidth model.
