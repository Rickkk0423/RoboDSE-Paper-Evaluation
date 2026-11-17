# Calibration Versions

These files have different evidential status. Do not select solely by filename.

| File | Status | Intended use |
| --- | --- | --- |
| `dram_v0_prior.json` | Analytical prior, no native measurements | Baseline and sensitivity comparison |
| `dram_v1_hbm2_8ch.json` | Historical native fit; all-ratio nominal mix failed overlap replay | Preserve failed-fit evidence, not a recommended nominal model |
| `dram_v2_hbm2_8ch.json` | Conditional balanced-stream native reference with broad empirical bounds | Conservative sampled DSE for the pinned HBM2 setup |

V2 has `eta_seq=0.5263309139` and `eta_mix=0.6650287744`. At the configured
256 GB/s physical peak these imply 134.7407 GB/s isolated and 89.6065 GB/s
balanced mixed bandwidth. The mixed envelope is 70.4124-195.1622 GB/s. Bounds
are padded empirical ranges, not confidence intervals or proven global limits.

V2 passes model-paced isolated/overlap replay but fails the independent nominal
mixed-capacity gate by about 42%; the tested held-out cases remain inside its
interval. Address phase alone changes balanced bandwidth by 35.65% under the
pinned mapper/controller/global-FIFO issue policy. A single mixed factor is not
validated across arbitrary layouts, ratios or queue policies.

The native setup is eight-channel HBM2, HBM2_2Gb / HBM2_2000Mbps, FRFCFS/Open,
issue width 8 and at most 512 outstanding 32-byte native transactions. Calibration
records source, binary and expanded-configuration hashes. Priority is unsupported:
`prio_leak=0` and its range are retained priors, not fitted measurements. RW cases
are diagnostics and do not calibrate a write penalty. Compute, area, energy and
task-success models remain uncalibrated. These are simulator, not silicon, data.

See `../../docs/PHASE2_RESULTS.md` for validation failures and matched DSE results.
