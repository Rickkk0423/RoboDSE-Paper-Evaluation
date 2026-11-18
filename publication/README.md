# Full experiment evidence

The GitHub repository (public as verified on November 18, 2026) contains review-sized paper tables and all project
code. The `v7-full-evidence` Release contains the full local payload, including
all historical results, failed runs, cold-storage archives, native snapshots,
dependency source snapshots, and handoff provenance. Python environments,
caches and Git internals are reproducible infrastructure and are excluded.

Download all `full-evidence.tar.gz.partNNN` files, `SHA256SUMS` and
`FULL_EVIDENCE_MANIFEST.json` from the same Release. Check before extraction:

```sh
shasum -a 256 -c SHA256SUMS
mkdir restored_evidence
cat full-evidence.tar.gz.part* | tar -xzf - -C restored_evidence
cd restored_evidence
uv sync --locked --all-extras --python 3.12
.venv/bin/python handoff/verify_snapshot.py
.venv/bin/python handoff/verify_deliveries.py
```

Restore into a fresh empty directory, not on top of a working checkout. The
outer archive contains cold archives without expanding them; use the project's
restore script only when a particular historical experiment requires those files.
Historical absolute paths remain provenance, not instructions to execute them.

Publication completion is established only by `UPLOAD_VERIFICATION.json` after
the remote asset names and sizes match the manifest. A draft Release or local
archive alone is not proof of upload. No new task episodes are represented here.

## November 18 Supplement

The fresh no-batching DSE campaign and Evaluation updates are documented in
`v9_no_batching/README.md`. Its separate Release supplements, rather than
replaces, the frozen V7 archive. Repository visibility is not changed by this
delivery; the earlier description of this repository as private is historical.
