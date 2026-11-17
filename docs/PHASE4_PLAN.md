# Phase 4: Near-Balance And Temporal-Order Controls

Date: 2026-11-15. This is a diagnostic experiment, not a fit or a DSE model
replacement. Device, mapper, controller, native FIFO issue width and outstanding
limit stay pinned to Phase 2. All traces offer saturated reads at time zero.

## Design Fixed Before Execution

| Group | Conditions | Cases |
| --- | --- | ---: |
| Dense ratio | 4 MiB, VLM shares 40/45/48/49/49.5/49.9/50/50.1/50.5/51/52/55/60%, shifts 0/4096 B | 26 |
| Size transfer | 16 MiB, shares 49.9/50/50.1%, both shifts | 6 |
| Fixed global ratio | 4 MiB, 50:50 overall, paired 40:60 then complementary skew, 1/16/256 epochs, both shifts | 6 |
| Fixed global ratio | 4 MiB, 50:50 overall, shuffled labels with seeds 17/29, both shifts | 4 |
| Generator control | Legacy floating accumulator vs exact integer accumulator at 49/50/51%, 4 MiB, both shifts | 6 |

Total: 48 native cases. Requested ratios are quantized to whole 64-byte requests;
reports retain actual counts and ratios. New uniform schedules use integer
accumulation to bound prefix discrepancy without floating-point drift. Legacy
generator controls retain the old implementation unchanged. Each stream still
walks its own contiguous address sequence in order. Fixed-ratio controls have
identical per-stream traffic/address sequences; only stream-label order changes.
The random controls use a local seeded PRNG and do not change global RNG state.

The manifest is written before trace generation. Offered descriptors are written
before native execution: switch fraction, run lengths, maximum/mean absolute
cursor skew and fraction of prefixes with skew <= 1/4/64 KiB. Cursor skew is
the byte difference between progress through the two streams, ignoring base
offset. It is not a decoded bank-conflict measure or an accepted-queue metric.
Native row/queue statistics are joined only as post-execution diagnostics.

## Questions

1. Is the bandwidth depression confined to exact equality, or a finite neighborhood?
2. Does its width depend on traffic size and accumulated relative stream progress?
3. Can traces with identical global ratio and addresses have different capacity?
4. Do legacy floating scheduling details materially affect the observed result?

No regression is fitted on this diagnostic set. Any future predictor needs a
new train/validation protocol and independent workload inputs before DSE use.

## Reproduce

```bash
uv run python vlasim/ramulator_bridge/probe_balance.py --backend .native/backend --config configs/hbm2_8ch.json --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/balance_phase4
```

On Einstein, submit `scripts/einst_balance.sh` in the isolated remote checkout.
Output paths are non-overwriting; the runner records trace, configuration,
library and source identities and verifies per-stream completion counts.

The executed run uses `/tmp/vlasim_phase4_20261115.Os3Bob` on node `einstein`
because the shared scratch mount rejected new writes with a quota error. The
environment/backend are symlinks to the unchanged previous isolated build;
project sources and new results are node-local. Node-local storage is not an
archive: copy reports and losslessly archived, hash-verified traces back locally
before relying on this run as evidence.
