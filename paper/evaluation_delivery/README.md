# RoboDSE Evaluation delivery

## Open these files

- `RoboDSE_Evaluation.vsdx`: new three-page Visio document, with editable native
  text, bars, lines, point markers, and heatmap cells. No bitmap chart substitutes.
- `review.pdf`: complete three-subsection Evaluation with figures and captions.
- `evaluation.tex`: manuscript body, ready for integration with the main paper.
- `review.tex`: standalone review wrapper, starting at Section 5.
- `data_guide/EVALUATION_DATA_AND_ORGANIZATION.md`: detailed Chinese subsection
  outline, exact panel values, axes, captions, claim boundaries and per-panel CSVs.

Pages: E1 merges batching traffic and timing; E2 presents hardware DSE and
no-batching ablation; E3 shows task-space SR projection. E3 is explicitly not
in-loop validation. No new robotic episodes were run.

The reference DATE Visio file is unchanged. Font and palette choices follow its
Times New Roman and blue-gray/red-brown scientific-figure conventions. Data
marks carry native Visio Shape Data with their source row or coordinate values.
Each page has separate Labels, Data marks, and Axes and guides layers, so text
and data can be selected or hidden separately while editing.
The figures are editable shapes, not live spreadsheet-linked charts. Regeneration
overwrites the generated document, so preserve manual edits in a separate copy.

## Evidence

- Existing selection study: `results/v8_no_batching/`.
- New main DSE ablation: `results/v9_no_batching_domain/`.
- Earlier unpruned main case: `results/v8_no_batching_case_final/`.
- Earlier local trial: `results/v8_no_batching_case/`; superseded by the final
  run, which records corrected new-run raw-evidence links and explicit failed
  check accounting. It is not used in the manuscript or figure sources.
- Frozen V7 and v8 task-projection sources remain unchanged.

The new campaign enumerates all 576 V7-retained hardware identities and every
legal core split, with five pipeline organizations plus serial, without
incumbent pruning. Its 16,416 configurations reuse 4,113 exact operation-template
semantics and yield 82,070 accepted candidate identities. Ten curve identities
fail the unchanged periodic gate. All 510 frontier identities pass consistency
checks, using 132 unique 960-request runs. Full versus no batching reproduces
5 improved / 3 extended / 14 identical frontiers; no batching versus serial is
identical in all 22 boxes. Counts persist in refreshed-only and 3D SRAM checks.
This is a finite search over retained hardware identities, not a global
continuous-period optimum, physical validation, or independent task trials.

Source reconciliation: the old V7 prose says two identical frontiers are empty.
The frozen `pareto_comparison.csv` and the reproduced three-arm comparisons
instead contain nonempty fronts for every one of the 22 boxes. This manuscript
follows the actual tables, and does not repeat the old prose statement.

## Validation and limits

`visio_validation.json` records ZIP/XML and independent libvisio parsing and
rendering. `layout_checks.json` uses Chrome to check the actual libvisio-rendered
text bounds; all three pages have zero detected overlaps or out-of-page text.
There has been no Microsoft Visio application open/edit test on this Mac.
Image inspection was unavailable to the agent; automated checks do not replace
the author's visual review. PNG previews and rendered SVGs are supplied.

`pdf_validation.json` records LaTeX compilation, page bounds and rasterization.
`figure_manifest.json` records data sources, hashes, and native shape counts.

## Rebuild

Run from the project root:

```sh
.venv/bin/python scripts/document_evaluation_data.py
.venv/bin/python scripts/build_evaluation_visio.py
.venv/bin/python scripts/verify_evaluation_visio.py
uv run --no-project --with playwright python scripts/check_figure_layout.py
uv run --no-project --with pymupdf python scripts/build_evaluation_review.py
```

Requires the supplied reference document at its original path, libvisio,
rsvg-convert, Chrome, TeX Live and Poppler. The Visio builder uses the Python
standard library and the existing task interpolation dependency. Playwright
and PyMuPDF are resolved in isolated uv tool environments, not added to the
project lock. PyMuPDF checks PDF text bounds; the installed pdftotext failed on
this document, while pdftoppm rasterization succeeded.

Repeat the main-case experiment into a fresh directory:

```sh
.venv/bin/python scripts/run_no_batching_case.py --out results/NEW_CASE_DIRECTORY
```

Repeat the broader ablation with `scripts/run_no_batching_domain.py --out
results/NEW_DOMAIN_DIRECTORY --workers 4`. Audit the default completed campaign
with `scripts/audit_no_batching_domain.py`.

5.1 defines the three DSE arms and fresh enumeration. 5.2 keeps its fixed-hardware
mechanism comparisons. 5.3 uses the broader unpruned ablation, followed by task
interpretation and limitations. Independent physical calibration and robotic
closed-loop validation are not claimed as completed. V7 cost/stress and SR
coverage statistics have not been rerun on the fresh candidate population.
