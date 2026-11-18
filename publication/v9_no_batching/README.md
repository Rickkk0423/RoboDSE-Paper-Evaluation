# Fresh no-batching DSE and Evaluation supplement

Release tag: `v9-no-batching-dse-20261118`.

## Results

- 576 V7-retained hardware identities, 16,416 independently enumerated mappings,
  4,113 unique operation-template semantics, no incumbent-based pruning.
- 82,080 attempted mapping/period identities; 82,070 accepted and 10 rejected
  by the unchanged periodic gate. All exclusions are recorded.
- No batching versus serial: identical resource frontiers in all 22 boxes.
- Full versus no batching: 5 strict improvements, 3 extensions, 14 identical.
  Counts persist with refreshed-only eligibility and a third SRAM dimension.
- 510 frontier identities pass 132 unique 960-request / 192-warmup consistency
  checks. Maximum mean-L/S relative discrepancy: 2.114788429638855e-11.
- Independent audit verified 4,245 raw file hashes and all configuration curves.
- Test suite: 350 passed. No robotic task episodes were run.

Strict improvement means at least one alternative vector dominates a baseline
vector, not universal dominance. This finite hardware/mapping/period search is
not a continuous global optimum or physical hardware validation. SR figures are
bounded interpolation diagnostics, not measured DSE task-success gains. Frozen
V7 area, stress and task-grid coverage statistics were not rerun on the new pool.

## Repository deliverables

- `paper/evaluation_delivery/evaluation.tex` and `review.pdf`: updated manuscript.
- `paper/evaluation_delivery/RoboDSE_Evaluation.vsdx`: native editable figures.
- `paper/evaluation_delivery/data_guide/`: Chinese organization guide and CSVs
  for every figure panel.
- `scripts/run_no_batching_domain.py`: broader fresh enumeration.
- `scripts/audit_no_batching_domain.py`: inventory and raw-hash audit.
- `scripts/document_evaluation_data.py`: rebuild the figure data guide.
- The other new scripts/tests preserve the retained-selection study, primary-case
  search, figure generation and verification.
- Summary JSONs in this directory allow review without downloading raw evidence.

## Release payload

`no-batching-dse-evidence.tar.gz` contains these complete result directories:

1. `results/v8_no_batching/`: historical retained/matched-support comparison.
2. `results/v8_no_batching_case_final/`: authoritative unpruned primary case.
3. `results/v9_no_batching_domain/`: fresh broader campaign, all search/recheck
   NPZ evidence, configuration inventories, candidate tables, exclusions and audits.

Only rebuildable `periodic.dylib` binaries are excluded. Superseded trial outputs,
virtual environments, caches and LaTeX intermediates are not included. Existing
V7 inputs, compute snapshots and calibration dependencies remain in the previous
`v7-full-evidence` Release. Do not interpret historical absolute provenance paths
as portable execution commands.

Download the archive, `SHA256SUMS`, and `EVIDENCE_MANIFEST.json` from the new
Release. Verify and inspect before extracting into a fresh directory:

```sh
shasum -a 256 -c SHA256SUMS
tar -tzf no-batching-dse-evidence.tar.gz
mkdir restored_v9
tar -xzf no-batching-dse-evidence.tar.gz -C restored_v9
```

Use a checkout at the Release commit, restore V7 dependencies following
`publication/README.md`, and place the new result directories under its
`results/` without overwriting unrelated work. To reproduce rather than inspect:

```sh
uv sync --locked --all-extras --python 3.12
.venv/bin/python scripts/run_no_batching_domain.py --out results/REPRODUCTION --workers 4
```

The default-path independent audit also checks original source manifests;
run it on the recorded source revision with the original V7 compute snapshot.
Figure rebuilding requires the original reference Visio, libvisio, TeX and
other tools listed in `paper/evaluation_delivery/README.md`. The delivered VSDX
can be edited without rerunning its builder. Automated parse/layout checks passed;
Microsoft Visio application testing and manual visual inspection were not completed.

`UPLOAD_VERIFICATION.json` records the completed remote Release verification:
all three published assets match local sizes and GitHub API SHA-256 digests.
The evidence archive contains 8,919 verified members and is 782,634,478 bytes.
The Release source commit is `bc0029854e3712d8328a07110929b7a81ad8ebe7`.
Run `scripts/verify_no_batching_upload.py` to repeat the remote check while the
local packaged assets remain available. A local archive or a draft Release alone
does not establish upload.
