# No-batching DSE ablation

Historical retained-population and primary-case study. The broader fresh,
unpruned campaign is now complete; use `evaluation_delivery/evaluation.tex`
and `../publication/v9_no_batching/README.md` for the current main results.
The conclusions below describe their original, narrower evidence scope.

## Execution and scope

Run ` .venv/bin/python scripts/ablate_no_batching.py --out results/NEW_DIRECTORY`
from the project root. Output directories must not exist. Frozen V7 was read only.
This is a new selection experiment over existing simulated candidates, not a new
hardware simulation campaign. No robotic episodes or new calibration were run.

The original search includes unbatched organizations but prunes configurations
using a shared incumbent. Supplemental same-split controls are not a complete
unbatched optimization search. Consequently, a filtered full-population result
alone cannot establish an exhaustive no-batching optimum.

Three arms use identical eligibility and Box rules: V7 serial reference;
joint selection with serial, k=1, and unbatched k=2/3; full joint selection.
The serial reference uses V7's L<=Smax rule. Both joint arms use actual L/S limits.

The matched-support check retains hardware/split/relative-period-factor groups
with all five pipelined organizations, plus serial candidates on those hardware
identities. It has 5,440 complete groups out of 10,490, 320 hardware identities,
and 28,800 candidate rows. This balances observed organization support, not
absolute launch periods or all originally pruned mappings. It is conditional on
retained successful curves and is not an exhaustive-search guarantee.

## Results across 22 Boxes

| Scope | Comparison | Strict improvement | Extension | Identical |
| --- | --- | ---: | ---: | ---: |
| Frozen retained candidates | no batching vs serial | 0 | 0 | 22 |
| Frozen retained candidates | full vs no batching | 5 | 3 | 14 |
| Matched support | no batching vs serial | 0 | 0 | 22 |
| Matched support | full vs no batching | 5 | 0 | 17 |

These classification counts are unchanged when conditional NoRefresh memory
configurations are removed, or total SRAM is added as a third Pareto dimension.
All 22 frontiers are nonempty in these tables; consult the both_empty field. A strict
classification uses the existing V7 rule: at least one alternative frontier
vector strictly dominates a baseline vector, not every vector dominates every
baseline vector. Counts do not establish identical individual designs across
the sensitivity settings.

The five strict improvements survive the matched-support check. The three
extensions in the full retained population do not: they must remain hardware
exploration results rather than matched-support causal batching evidence.
No-batching's identical resource fronts do not imply identical L/S values or
absence of all possible pipelining benefits.

## Manuscript integration

- 5.1: add three-arm definitions and retained/matched candidate support rules.
- 5.2: retain controlled mechanism results; distinguish this fixed-split ablation
  from joint selection in 5.3. No replacement experiment is needed.
- 5.3: after resource-frontier overview add the no-batching comparison, followed
  by the matched-support qualification. A small four-row table is sufficient;
  resource plots can overlay three arms, noting serial/no-batching overlap.
- Do not claim unpruned global optimality, new hardware validation or SR gains.
- If exhaustive attribution of the three extensions is needed later, evaluate
  missing mappings independently of the full-method incumbent. A bounded
  unpruned primary-case follow-up is now completed as described below; the
  remaining global search domain has not been exhaustively rerun.

Artifacts: results/v8_no_batching/{summary.json,coverage.csv,
box_comparisons.csv,frontier_points.csv}. Summary records source and script hashes.

## Unpruned primary-case follow-up

`results/v8_no_batching_case_final/` contains a fresh independent search for
LPDDR5 at 102.4 GB/s with four cores: eight SRAM variants, every VLM/DiT split,
five pipeline organizations and serial, totaling 128 configurations. No
incumbent pruning is used. The 32 unique operation semantics yield 640 candidate
identities; 160 unique 960-request checks pass with no failed checks.

For Box(200,100), serial and no-batching have zero feasible candidates; full
RoboDSE has 16. The fastest-refresh feasible full candidate has L/S of
178.16/89.07 ms. This directly supports enabling the main low-bandwidth design,
without asserting a full-space or continuous-period global optimum.

The latest integrated manuscript and editable Visio are in
`paper/evaluation_delivery/`. No robotic task episodes were run.
