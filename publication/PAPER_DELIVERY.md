# Paper delivery scope

Repository: Rickkk0423/RoboDSE-Paper-Evaluation (private).

## Read in this order

1. paper/EVALUATION_PLAN.md: evidence contract and proposed structure.
2. paper/evaluation_draft.tex: bounded four-subsection Evaluation draft.
3. paper/INTRODUCTION_ALIGNMENT.md: replacement claims consistent with evidence.
4. results/v8_eval_prep/summary.json and CSV tables: newly computed projections.
5. docs/CASE_V7_REPORT.md: frozen hardware evaluation and caveats.
6. publication/README.md: complete Release evidence restoration.

## Newly executed

- Convex-hull projection of 39,928 frozen candidates: 17,992 covered, 21,936 excluded.
- Controlled batching projections, with exact table-based estimates rather than
  substituting the 49.85% measured peak for nearby hardware coordinates.
- Exact-hardware descriptive comparison using the actual min-L serial baseline
  before consulting task coverage: 264 pairs all abstain from an SR gain claim.
- Four new regression cases for the example and hull-boundary exclusion.
- Relocated-project regression and historical evidence verification.

## Not executed / not claimed

- No new native campaign, heldout calibration, task episode or cross-host validation.
- No matched-success hardware saving is inferred from timing-box membership alone.
- No final publication-quality figure set: V7 CSVs and existing preview are included.
- No final matched-SR resource threshold table; lacking baseline coverage prevents
  a fair all-design comparison. Covered-only frontiers would be diagnostic and
  cannot resolve the missing low-latency task measurements.
- No verified attribution of the legacy CSV to checkpoint/H=16 from CSV metadata.
- No claim of total system energy or physical area reduction.

The archive was frozen before later upload tooling and regression additions;
the repository contains those later additions. Existing frozen experiment results
are unchanged. `handoff/PACKAGING_SHA256.json` records the earlier local handoff,
not the current GitHub layout; use the Release manifest and upload verification
for this publication, and original delivery manifests for frozen experiments.
