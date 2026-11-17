# Storage Cleanup, 2026-11-16

Completed: 15 intermediate directory trees compacted; net allocated-space saving
3,587,330,048 bytes (3.34 GiB, excluding the small cache saving). The workspace
now occupies approximately 14 GiB. All six historical delivery manifests passed
post-cleanup artifact checks, with no checksum mismatches. Seven archive and
restoration safety checks also passed. The full simulator suite was not rerun:
this operation does not change simulator code, and archived inputs must be
restored before running validators that require their original disk paths.

Cold intermediate evidence has been compacted into lossless gzip tar archives in
`results/_cold_storage_20261116/`. The expanded copies are removed only after
every archived file has been checked against its source SHA-256 and a second
source check confirms no concurrent change.

Final reports, summary tables, figures, source code, native backends, the virtual
environment, cost sources, and delivery manifests remain in their existing
locations. Failure evidence inside compacted directories is retained in the
archives, not discarded. Python and pytest caches are disposable and removed.
This operation is limited to the local project; no remote data is deleted.

## Audit Records

- `results/_cold_storage_20261116/cleanup_manifest.json`: exact directories,
  file counts, archive checksums, verification and deletion status, space totals.
- `results/_cold_storage_20261116/*.index.json`: original relative paths,
  file SHA-256, sizes, timestamps and permissions.
- `results/_cold_storage_20261116/preserved_files.json`: checksums of the
  nonarchived result files, original reports and implementation files checked
  unchanged during cleanup. Finder's `.DS_Store` is excluded from the unchanged
  evidence assertion: `results/v6/.DS_Store` was automatically updated while the
  operation ran, and this metadata change is explicitly recorded.
- `results/_cold_storage_20261116/post_cleanup_delivery_verification.json`:
  original delivery checksums compared against remaining files and verified
  archive indexes; all passed.

Original delivery manifests are historical records and have not been rewritten.
Their checksums remain applicable to archived bytes, but existing validators
that expect all paths on disk require restoration first. Do not rerun the
finisher or evidence-producing jobs against missing cold directories: those
programs are not archive-aware and may regenerate outputs.

## Restoration

Run from the project root using the existing Python environment. To restore
one directory, pass its original project-relative path:

```sh
.venv/bin/python scripts/compact_results.py --restore results/v6/dse/shards
```

To restore every archived directory:

```sh
.venv/bin/python scripts/compact_results.py --restore all
```

Restoration verifies archive checksums and every file hash, refuses to overwrite
existing files, and retains the compressed archives. Ensure sufficient free
space before restoring all directories. Original file bytes and permissions are
restored; exact filesystem timestamps are not restored.
