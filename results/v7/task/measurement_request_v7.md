# V7 Task Measurement Request

Exactly16 proposed timing points; zero closed-loop task episodes were run.
The two main Boxes have no strict resource-dominating pairs. Their rows test actual resource alternatives, not a nonexistent dominance claim.

| Point | Hardware | Mapping | L/S(ms),960 | Priority | Supported Claim |
| --- | --- | --- | --- | --- | --- |
| v6p007690 | HBM2_c8_c6_s8_p512 | pipelined/k2 batched | 99.683/49.850 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p007680 | HBM2_c8_c6_s8_p512 | pipelined/k3 batched | 141.674/47.225 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p012380 | LPDDR5_c16_c8_s8_p512 | pipelined/k2 batched | 92.507/46.295 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p012330 | LPDDR5_c16_c8_s8_p512 | pipelined/k3 batched | 128.704/42.908 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p016290 | LPDDR5_c32_c2_s8_p512 | serial/k1 batched | 97.350/97.399 | 2 | Box(200, 100): test latency_only resource alternative (2, 409.6); extension or equality is not strict resource improvement. |
| v6p011000 | LPDDR5_c16_c3_s8_p512 | serial/k1 batched | 85.697/85.719 | 2 | Box(200, 100): test latency_only resource alternative (3, 204.8); extension or equality is not strict resource improvement. |
| v6p024480 | LPDDR5_c8_c4_s8_p512 | pipelined/k2 batched | 178.164/89.073 | 2 | Box(200, 100): test task_aware resource alternative (4, 102.4); extension or equality is not strict resource improvement. |
| v6p023970 | LPDDR5_c8_c2_s8_p512 | serial/k1 batched | 141.620/141.661 | 2 | Box(250, 150): test latency_only resource alternative (2, 102.4); extension or equality is not strict resource improvement. |
| v6p002174 | HBM2_c16_c16_s16_p512 | serial/k1 batched | 24.948/31.208 | 3 | Low-latency reference near25ms to locate the left boundary of a task-performance plateau. |
| v6p036392 | HBM2_c32_c12_s16_p512 | pipelined/k2 batched | 50.007/21.025 | 3 | Low-latency reference near50ms to locate the left boundary of a task-performance plateau. |
| v6p014878 | LPDDR5_c32_c16_s16_p512 | pipelined/k2 batched | 74.987/50.006 | 3 | Low-latency reference near75ms to locate the left boundary of a task-performance plateau. |
| v6p031612 | GDDR6_c24_c12_s16_p512 | pipelined/k3 batched | 95.031/26.813 | 3 | Low-latency reference near95ms to locate the left boundary of a task-performance plateau. |
| v6p020680 | LPDDR5_c4_c3_s8_p512 | pipelined/k2 batched | 337.677/168.868 | 4 | Outside-platform counterexample near338/169ms: test whether optimistic platform extrapolation fails. |
| v6p025542 | LPDDR5_c4_c4_s16_p512 | pipelined/k2 unbatched | 451.468/225.745 | 4 | Second outside-platform counterexample: task quality must not be inferred from timing alone. |
| v6p026106 | GDDR6_c16_c12_s8_p512 | pipelined/k3 batched | 149.920/56.222 | 5 | Intermediate latency control to test the shape between low-L references and outside-platform examples. |
| v6p026466 | GDDR6_c16_c12_s16_p512 | pipelined/k3 batched | 149.920/56.222 | 5 | Intermediate latency control to test the shape between low-L references and outside-platform examples. |

## Required External Protocol Inputs

Environment/version, policy checkpoint, speed bands, trial budgets, random seeds, latency injection, action chunk rules and episode deadlines remain null until the author supplies them.
Record every episode, including invalid episodes, with exact point_id, environment/checkpoint hashes, seed, L/S injection, wall time, success, invalid flag and invalid reason.
Report both protocols: invalid-as-failure uses all attempted episodes as denominator; invalid-excluded uses valid episodes only. If all attempts are invalid, invalid-excluded success rate is null, never zero.
No guessed checkpoints, fabricated episodes, inferred success rates or unexecuted speed bands may appear as results.
Use the unchanged V6 real-result validator only after genuine records are supplied: `PYTHONPATH=vlasim .venv/bin/python vlasim/v6_task.py validate --input <real_records.json> --output <new_validation.json>`.
Timing checks here are simulator rechecks, not closed-loop task evaluation.
