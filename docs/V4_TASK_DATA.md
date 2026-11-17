# V4 P1-B Task Data Preparation

## Status

`blocked_missing_closed_loop_environment`. Preparation and bounded environment
inspection are complete; **no new task episodes, training or closed-loop evaluation
were run**. This is not a completion claim for P1-B supplemental measurement.

The inspected specification is `/Users/mr.meeseeks/Downloads/NEXT_STEPS_V4.md`.
Its document date is November 16, 2026; the environment inspection took place on
November 15, 2026 (remote clock: `2026-11-15T19:41:44Z`).

## Observed Evidence

- `vlasim/data/libero_dynamic_L_S.csv` contains 33 aggregate rows, with three
  speed headers: 0.03, 0.06 and 0.09 m/s. Those are observations of the legacy CSV,
  **not a confirmed speed protocol for either new benchmark**. The CSV has an
  aggregate valid-count column, but no per-speed trial denominators, trial outcomes,
  checkpoint hashes, environment versions, injection or adoption metadata.
- `vlasim/analysis/README.md` and `vlasim/analysis/task_report.py` explicitly say
  that this CSV cannot recover an exact pooled binomial estimate or standard error.
- A bounded repository filename search (including results, excluding native source,
  virtualenvs and Git internals) found only that CSV for checkpoint, episode,
  trial, LIBERO, openpi, safetensors and ckpt patterns. This cannot exclude an
  artifact with a different name or in an uninspected location.
- Local `.venv/bin/python` and einst's `/usr/bin/python3`, project `.venv`, and
  project `.venv_complete` all returned `find_spec(...) is None` for `libero`,
  `openpi`, `mujoco`, `robosuite`, `torch` and `jax`.
- On einst (`einstein`), the two known project roots were inspected to depth 3:
  `/tmp/vlasim_phase4_20261115.Os3Bob` and
  `/scratch/renati/vlasim_dse_20261115_phase2`. Filename checks found only the legacy
  task CSV, not a checkpoint or episode artifact. The first project's `inputs`
  contains hardware `robust_LS.csv` and `shortlist.csv`, not closed-loop episodes.

The inspection did not search credentials, all users' homes, model caches, the
entire machine, or arbitrary mounts. No checkpoint identity/version or executable
LIBERO-Dynamic/Long closure was verified in the inspected scopes. Absence here
does not establish absence everywhere on einst.

Machine-readable observations: `results/v4/task_data/environment_check.json`.

## Collection Plan

`results/v4/task_data/sampling_plan.json` expands both benchmarks separately:

- Low latency: 6 points per benchmark from L={25,50,75}, S={25,50,75}, S<=L.
- Plateau: 22 points per benchmark from L={100,125,150,175,200,250},
  S={50,75,100,150}, S<=L.
- Total: **56 benchmark/L/S points**, not 56 episodes. Each point has
  `speed_levels: null` and `episodes_per_speed: null`, pending the real protocol.
  Legacy overlap does not count as completion because trial provenance is absent.

Required external inputs: a pi0.5 checkpoint ID/version/hash and access path;
executable benchmark entry points plus assets/dependency lock and benchmark,
environment and simulator versions; confirmed speed levels and per-speed episode
budgets; latency injection definitions and clock; action-chunk adoption strategy;
invalid-episode definition; and per-episode logs/results. No values are inferred
from `/360`, rounded rates, hardware simulations or the legacy speed headers.

## Trial Contract And Pooling

`vlasim/v4_task_data.py` is standalone and uses only the standard library.
`trial.schema.json` describes a **single real episode**. `example.template.json`
is a null-filled, non-ingestible template, not measured or synthetic trial evidence.
Synthetic complete episodes exist only inside `tests/test_v4_task_data.py`.

Required fields include benchmark/version, run/trial/episode/task IDs, seed,
positive L/S with S<=L, speed/unit, checkpoint/version/SHA-256, environment and
simulator versions and lock SHA-256, versioned injection definitions/config,
versioned adoption strategy/config, versioned validity definition, validity reason
(including for valid episodes), boolean success and evidence reference.
The Python validator additionally rejects missing/placeholder provenance,
nonfinite numbers, duplicate JSON keys, repeated trial/episode IDs within a run,
and invalid episodes claiming success. An invalid run's observed outcome belongs
in the raw evidence; its trial `success` must be false under this contract.
This validates structure and consistency, not the authenticity of external logs.

Grouping retains benchmark/version, L, S, speed, checkpoint, environment, injection,
adoption and validity protocol. Runs and tasks within exactly the same group pool
episode counts; rates are never averaged across runs/tasks or speeds.

- `invalid_as_failure`: p = successful valid episodes / all episodes.
- `exclude_invalid`: p = successful valid episodes / valid episodes.
- Both return plug-in binomial SE sqrt(p*(1-p)/n), numerator, denominator and
  valid/invalid counts. No valid episodes means null p/SE for the excluded policy.
- These are binomial descriptive estimates, not cluster-adjusted uncertainty or
  confidence intervals. Correlated episodes/tasks may need a separate analysis.

Usage after actual data collection:

```sh
.venv/bin/python vlasim/v4_task_data.py aggregate real_trials.jsonl --out pooled.json
```

All input lines are validated before output is created. Existing output files are
not overwritten. The aggregate report includes the source JSONL SHA-256. There is
currently no real trial JSONL and no measured pooled-rate output in this delivery.

Preparation is reproducible in a **new** output directory:

```sh
.venv/bin/python vlasim/v4_task_data.py prepare \
  --out results/v4/task_data_fresh \
  --source-csv vlasim/data/libero_dynamic_L_S.csv \
  --spec /Users/mr.meeseeks/Downloads/NEXT_STEPS_V4.md
```

## Verification

Run `.venv/bin/python -m pytest tests/test_v4_task_data.py -q`.
Tests cover exact plan expansion, required metadata, malformed JSONL, duplicates,
nonfinite values, invalid conventions, all-invalid groups, group separation,
unequal-denominator pooling and template rejection. No real task execution occurs.

Observed verification: **51 new tests passed**; combined with the four existing
`tests/test_task_report.py` tests, **55 passed in 1.16 seconds**. Preparation CLI
reported 56 points, zero measured trials and the blocked status. No other
agents' files or frozen experiment results were modified for this task.
