# Evaluation: evidence before claims

This artifact supports the supplied RoboDSE manuscript. It does not validate its
citations or claim to have rerun the closed-loop experiments in Section 3.

## 5.1 Setup and evidence contract

Separate calibrated native DRAM measurements, analytical/hybrid hardware timing,
960-request scheduler consistency, imported aggregate task data, and real task
rollouts. State model/checkpoint, H, adoption and delay semantics when verified.
The legacy 33-row CSV does not itself verify pi0.5/H=16 identity or episode provenance.
Use the actual convex hull, not only L>=100 and S>=50 rectangle tests.
Report coverage and abstentions for every selection comparison. Quantify unique
hardware identities directly from input tables; do not copy an unverified grid count.

## 5.2 Cross-chunk batching: controlled mechanism

Use F2/F5 with fixed physical hardware AND VLM/DiT split. Compare k=1, k=2/3
batched and k=2/3 unbatched. Plot traffic, L/S, compute and exposed-memory time.
Include low-bandwidth LPDDR5 and compute-limited HBM2 counterexamples.
The 120.55/120.54 ms LPDDR5 point is k=1 pipeline, NOT the best serial mapping.
Compare batched/unbatched at matched k for the causal batching effect, and compare
k=1 against larger k only as an execution-organization tradeoff.
Traffic ratios imply same-type dynamic DRAM energy ratios under a fixed coefficient,
not total accelerator power savings. Busy fraction can fall when work is amortized;
it is not sufficient evidence of worse array efficiency.

## 5.3 DSE: primary hardware-resource result

Frozen V7: 5 strictly better, 3 extended, 14 identical resource fronts across 22
Boxes. These are timing feasibility Boxes, not measured equal-success contours.
Box(200,100) trades an extra core for half the peak bandwidth; it is not strict
resource dominance or same-hardware-budget improvement. S<=50 strict improvements
cannot establish task success on a grid with no S<50 coverage.
Area, SRAM as a third resource, and bandwidth stress are secondary sensitivities.
Central literature coefficients give 0/22 strictly smaller-area Box selections.
Pairwise PHY break-even and global minimum-area selection answer different questions.

## 5.4 Task-space projection: bounded estimate

Overlay achievable L/S paths on the measured grid and its convex hull. Interpolate
only inside the hull, retain the coverage counts, and distinguish measured grid
vertices from projected hardware points. Do not assign the 49.85% value at
(200,100) to (178.16,89.07); compute the latter explicitly.

For same-budget comparisons, control all relevant resources (including SRAM and
memory type), and define the latency-only optimizer before looking at the SR grid.
If its true min-L design is outside the hull, mark comparison unavailable. Never
choose a slower covered baseline to manufacture improvement. Matched-SR resource
frontiers should be reported only over covered candidates, with explicit coverage
selection bias. No statistical significance follows from this aggregate table.

## Manuscript edits required

- Replace the Introduction's unsupported area/power and xx claims with quantified
  hardware-resource results plus explicitly estimated task-space results when ready.
- Replace 'Selected designs are then validated through direct closed-loop simulation'
  with 'Selected designs are designated for direct closed-loop validation' until
  actual episodes with matching timing and execution semantics have been collected.
- Do not present this projection as new experiments across all Section 3 models.
  Other task surfaces require their own provenance and execution protocol.
- The action-age formula is explanatory, not a guaranteed success surrogate.
  In the LPDDR5 example batching can raise L+S/2 while reducing S; the task response
  must be learned from observations rather than inferred from average age alone.

Reproduce the preparation in a fresh output directory with
`python scripts/prepare_paper_evaluation.py`. Frozen results/v7 is never modified.
