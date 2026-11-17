# DSE subdirectory reorganization

The active project root is `/Users/mr.meeseeks/gemini/DSE`.
All DSE code, results, native snapshots, Git metadata and handoff materials were
moved together from the parent directory. `../Ramulator` remains separate.
The environment was rebuilt for the new path using the locked dependencies.
Original Orca workspaces remain unchanged. Historical absolute provenance paths
are not rewritten. Earlier layout documents are retained in layout_v1_snapshot.

Subsequent paper preparation is isolated under results/v8_eval_prep and paper/.
GitHub publication uses normal Git for code and review-sized paper data, and a
checksummed split Release archive for full local evidence. Publication status is
recorded in publication/ rather than asserted from this plan.
