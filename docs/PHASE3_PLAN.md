# Phase 3: Conditional Mixed Bandwidth

This experiment tests a conditional lookup before changing analytical DSE.
Phase 2's scalar v2 and its failed nominal-capacity gate remain unchanged.

## Predeclared Design

Native device, mapping, controller, FIFO issue policy and outstanding limit stay
fixed to Phase 2. All traffic is saturated all-read sequential stream pairs.
The experiment manifest is written before traces execute; fit uses training
rows only. The threshold is absolute bandwidth prediction error <= 10% for
every supported held-out case, not just a group average.

| Split | Conditions | Count |
| --- | --- | ---: |
| Train | Shifts 0/512/4096/65536 B, ratios 25/50/75%, sizes 1/4 MiB | 24 |
| Held-out size | Same shifts/ratios, 16 MiB | 12 |
| Held-out ratio | Same shifts, ratios 40/60%, sizes 4/16 MiB | 16 |
| Unsupported layout | Shift 64 B, all five ratios, sizes 4/16 MiB | 10 |

Fit the median bandwidth of 1/4 MiB training sizes at each shift and ratio.
Predict between training ratios by linear interpolation at an exactly supported
shift. Do not interpolate address shifts or extrapolate ratio. Unsupported
layouts must yield abstention, not a fabricated prediction or a passing gate.
This deliberately simple baseline tests whether conditions are sufficient.
Some conditions appeared in Phase 2 diagnostics; these are prospective split
assignments for this experiment, not a claim of wholly unseen research data.

Compare errors against the frozen v2 scalar. Keep failed interpolation results;
do not add held-out samples to the model and then call them validation. Native
row-hit/conflict and queue counters are diagnostic outputs only, not features
available to the current analytical simulator.

## Reproduce

```bash
uv run python vlasim/ramulator_bridge/layout_campaign.py --backend .native/backend --config configs/hbm2_8ch.json --calib vlasim/calib/dram_v2_hbm2_8ch.json --out results/layout_phase3
uv run python vlasim/ramulator_bridge/analyze_layout.py results/layout_phase3
```

Einstein submission uses `scripts/einst_layout.sh` and the same isolated remote
project. Source-only checkouts need the native dependencies and backend build
described in `NATIVE_WORKFLOW.md`. Output directories are non-overwriting.

## Integration Gate

Even successful bandwidth interpolation would validate only these conditions.
Before DSE integration, workload events need independently defined layout and
offered-ratio descriptors, and real operation/burst traces need their own tests.
Post-execution row counters cannot be used as runtime features without a separate
predictor. NeuSim shapes, task success, area and energy remain separate gates.

## Outcome

Execution and the subsequent controlled issue-order diagnostic are reported in
`PHASE3_RESULTS.md`. Size transfer passed, ratio interpolation failed, and unknown
layout prediction abstained as designed. The model is not integrated into DSE.
The diagnostic follow-up can be reproduced with:

```bash
uv run python vlasim/ramulator_bridge/probe_issue_order.py --backend .native/backend --config configs/hbm2_8ch.json --out results/issue_order_phase3
```

Use `scripts/einst_issue_order.sh` for the corresponding Slurm allocation.
