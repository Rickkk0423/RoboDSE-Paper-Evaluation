# analysis/ (downstream of the hardware simulator)

Not imported by `vlasim`. Consumes `data/sweep_LS.csv` (L/S per configuration) later, once the
hardware side is settled:
- `task_report.py`: descriptive interpolation of the imported measured grid;
  outside-hull candidates abstain. It reports candidate corner coverage, not a
  final hardware or continuous worst-case task ranking.
- `surface.py`: compatibility wrapper, unknown standard error is returned as
  `None`. The grid averages rates over speeds without per-speed denominators,
  so a binomial SE and an exact invalid-as-failure rate cannot be recovered.
- Hardware/task delay semantics and checkpoint/environment provenance must be
  verified before treating descriptive interpolation as task-aware selection.
