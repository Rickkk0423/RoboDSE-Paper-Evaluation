# CASE V7 Report

## 1. Status

V7 resource-Pareto data, secondary literature-cost sensitivities, selected-point timing checks and a16-point real-task measurement request are delivered. No new DSE grid, no new heldout DRAM experiment, no task episodes and no new cross-host validation were executed.

| section | status |
| --- | --- |
| 1 Cost patch | completed; two Micron centers author-supplied, not independently retrieved |
| 2 Resource Pareto | completed;22 Boxes, pre/post snapshots retained |
| 3 Secondary results | completed; correlated2000-draw area sensitivity; same-type energy ratios |
| 4 F1-F6 | completed; CSV source/scope comments plus one rough preview |
| 5 Rechecks/stress | 32288/32288 timing identities passed;3714/4740 stress rows stable |
| 6 Task request | 16 proposed points;0 real task episodes |

960 requests per timing check,192 warmup. 8325 exact-semantic compiled runs; 190 additional original-Python-scheduler references for frontiers/F2/area choices. Maximum relative L/S deviation: 7.4941e-10/2.4244e-10; maximum Python/compiled timestamp difference0s. Traffic and compute+exposed-memory/linear+attention time conservation passed. No >1e-6 cross-host difference was observed because no new cross-host comparison ran; frozen prior controls remain evidence, not a new-host claim.

| stage | tests | failures |
| --- | --- | --- |
| 00_baseline | 318 | 0 |
| 01_cost | 330 | 0 |
| 02_pareto | 330 | 0 |
| 03_secondary | 330 | 0 |
| 04_figdata | 330 | 0 |
| 05_validation | 333 | 0 |
| 06_task | 333 | 0 |
| 07_final | 337 | 0 |

## 2. Coefficient Patch

| coefficient | value | lower | upper | source_type | status |
| --- | --- | --- | --- | --- | --- |
| A_phy_LPDDR5 | 1.38 | 1.0 | 1.5 | academic | literature_estimate |
| A_phy_GDDR6 | 0.38391676682692305 | 0.30556640625 | 1.4259765625 | derived_ratio | literature_estimate |
| e_dram_LPDDR5 | 4.0 | 2.0 | 6.0 | vendor | literature_estimate |
| e_dram_GDDR6 | 7.5 | 4.9 | 11.3 | vendor | literature_estimate |

All are literature_estimate, never calibrated. All other V6 coefficients and2000 old draws are unchanged. LPDDR PHY source is a12nm LPDDR4X x32 design;2.89mm2 minus0.135mm2 sensor bumps, divided by2=1.3775, rounded1.38 perx16. Bump-limited, no process shrink; LPDDR4X->LPDDR5 proxy is unvalidated. Rambus equal256GB/s PHY ratio1.5-1.75 is directly verified. GDDR6 area draws equal HBM2 draw/32*28*ratio, not independent draws. Spartus TableVII independently verifies5.5pJ/bit only, not Micron7.5/6.0. Micron4 and7.5 centers are explicitly user-supplied vendor claims whose original documents were not independently retrieved. The specification upper11.3 is rounded from11.25. Source failures and extracted originals are retained undercost/sources/.

**cross_type_energy_comparable=false**. Micron device/module accounting and FGDRAM HBM2 accounting differ; there is no cross-type absolute-energy ranking. Same-type coefficients cancel in ratios.

## 3. Primary Resource Results

Before recheck:{'task_strictly_better': 5, 'identical': 14, 'task_extends': 3}. After recheck:{'task_strictly_better': 5, 'identical': 14, 'task_extends': 3}. Excluded timing identities:0. Nominal L/S were never silently replaced.

Pareto equality means equality of(n_cores,peak_BW) vector sets, not identical mappings/periods. Every tied hardware/mapping/SRAM/period identity is retained in the full point tables. Two empty frontiers are recorded asidentical (empty), not as evidence of feasibility. The latency-only PRIMARY definition follows V7 literally:serial L<=Smax, all retained periods. The SECONDARY global-area baseline follows frozen V6:serial Tmin only. These definitions are explicitly separate.

| statistic | value | matching_Box_core_rows |
| --- | --- | --- |
| minimum | 0.625 | (100,50),n=6; (150,50),n=6; (200,50),n=6; (250,50),n=6; (300,50),n=6 |
| median | 1.0 | (100,50),n=4; (100,75),n=3; (100,75),n=4; (100,100),n=2; (100,100),n=3; (150,50),n=4; (150,75),n=3; (150,75),n=4; (150,100),n=2; (150,100),n=3; (150,150),n=2; (200,50),n=4; (200,75),n=3; (200,75),n=4; (200,100),n=2; (200,100),n=3; (200,150),n=2; (200,200),n=1; (200,200),n=2; (250,50),n=4; (250,75),n=3; (250,75),n=4; (250,100),n=2; (250,100),n=3; (250,150),n=2; (250,200),n=1; (250,200),n=2; (300,50),n=4; (300,75),n=3; (300,75),n=4; (300,100),n=2; (300,100),n=3; (300,150),n=2; (300,200),n=1; (300,200),n=2 |
| maximum | 1.0 | (100,50),n=4; (100,75),n=3; (100,75),n=4; (100,100),n=2; (100,100),n=3; (150,50),n=4; (150,75),n=3; (150,75),n=4; (150,100),n=2; (150,100),n=3; (150,150),n=2; (200,50),n=4; (200,75),n=3; (200,75),n=4; (200,100),n=2; (200,100),n=3; (200,150),n=2; (200,200),n=1; (200,200),n=2; (250,50),n=4; (250,75),n=3; (250,75),n=4; (250,100),n=2; (250,100),n=3; (250,150),n=2; (250,200),n=1; (250,200),n=2; (300,50),n=4; (300,75),n=3; (300,75),n=4; (300,100),n=2; (300,100),n=3; (300,150),n=2; (300,200),n=1; (300,200),n=2 |

Bandwidth ratios are computed only at matched core counts where BOTH Pareto fronts have points; missing counts remain null and do not enter the distribution. Core ratios likewise require a matched bandwidth tier. SRAM(total shared+private) changes the3D nondominated identity set in22 Boxes; it is not part of the main2D dominance definition. Per-pair3D dominance is separately recorded.

Empirical stress:0/344 Box/task-identity memberships remain feasible in>=80% of scenarios (0.000%). 0/16640 matched strict pairs have BOTH ends feasible in>=80%. Individual task feasible fractions range46.667%-76.667%;none reaches80%. These are deterministic scenario fractions, not success probabilities, confidence intervals or independent validation. Counts retain SRAM/mapping/period identities;resource-collapsed counts must not be inferred from these totals. Old residuals transferred to repaired identities remain unvalidated. W1 DiT is unmeasured and unchanged.

### Box(200, 100): task_extends

Complete frontier identity table below; every row remains linked to its original V6 point.

| protocol | point_id | hardware_id | mode | vlm_cores | k | batching | L_ms | S_ms | n_cores | BW_peak_GBps | sram_shared_MB | private_KB_per_core | conditional_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| latency_only | v6p011000 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011001 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011002 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011003 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011004 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011005 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011006 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011007 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011008 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011009 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011060 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011061 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011062 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011063 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011064 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011065 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011066 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011067 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011068 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011069 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011120 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011121 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011122 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011123 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011124 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011125 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011126 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011127 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011128 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011129 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011180 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011181 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011182 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011183 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011184 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011185 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.69691742672728 | 107.14874488525459 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011186 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011187 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.69691742673972 | 128.57849386230535 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p011188 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p011189 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.69691742640222 | 171.43799181640273 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016290 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016291 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016292 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016293 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016294 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016295 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016296 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016297 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016298 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016299 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016300 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016301 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016302 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016303 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016304 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016305 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016306 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016307 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016308 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016309 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016310 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016311 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016312 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016313 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016314 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016315 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016316 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016317 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016318 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016319 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016320 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016321 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016322 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016323 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476476773 | 107.13871864007807 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016324 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016325 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476473434 | 121.74854390917962 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016326 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016327 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476469214 | 146.0982526910156 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p016328 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p016329 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476461524 | 194.79767025468567 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011000 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011001 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011002 | LPDDR5_c16_c3_s8_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011003 | LPDDR5_c16_c3_s8_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011060 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011061 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011062 | LPDDR5_c16_c3_s16_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011063 | LPDDR5_c16_c3_s16_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011120 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011121 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011122 | LPDDR5_c16_c3_s32_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011123 | LPDDR5_c16_c3_s32_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011180 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011181 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.6969174267086 | 85.71899590820381 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p011182 | LPDDR5_c16_c3_s64_p512 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p011183 | LPDDR5_c16_c3_s64_p2048 | serial | 3 | 1 | True | 85.69691742671696 | 94.29089549902413 | 3 | 204.8 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p016290 | LPDDR5_c32_c2_s8_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p016291 | LPDDR5_c32_c2_s8_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p016300 | LPDDR5_c32_c2_s16_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p016301 | LPDDR5_c32_c2_s16_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p016310 | LPDDR5_c32_c2_s32_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p016311 | LPDDR5_c32_c2_s32_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p016320 | LPDDR5_c32_c2_s64_p512 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p016321 | LPDDR5_c32_c2_s64_p2048 | serial | 2 | 1 | True | 97.35000476479694 | 97.39883512734367 | 2 | 409.6 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024480 | LPDDR5_c8_c4_s8_p512 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024481 | LPDDR5_c8_c4_s8_p2048 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024482 | LPDDR5_c8_c4_s8_p512 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024483 | LPDDR5_c8_c4_s8_p2048 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024520 | LPDDR5_c8_c4_s16_p512 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024521 | LPDDR5_c8_c4_s16_p2048 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024522 | LPDDR5_c8_c4_s16_p512 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024523 | LPDDR5_c8_c4_s16_p2048 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024560 | LPDDR5_c8_c4_s32_p512 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024561 | LPDDR5_c8_c4_s32_p2048 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024562 | LPDDR5_c8_c4_s32_p512 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024563 | LPDDR5_c8_c4_s32_p2048 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024600 | LPDDR5_c8_c4_s64_p512 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024601 | LPDDR5_c8_c4_s64_p2048 | pipelined | 3 | 2 | True | 178.1640358152364 | 89.07341015624652 | 4 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024602 | LPDDR5_c8_c4_s64_p512 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024603 | LPDDR5_c8_c4_s64_p2048 | pipelined | 3 | 2 | True | 187.05924504682966 | 97.980751171874 | 4 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |

### Box(250, 150): identical

Complete frontier identity table below; every row remains linked to its original V6 point.

| protocol | point_id | hardware_id | mode | vlm_cores | k | batching | L_ms | S_ms | n_cores | BW_peak_GBps | sram_shared_MB | private_KB_per_core | conditional_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| latency_only | v6p023970 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p023971 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p023972 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p023973 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p023974 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p023975 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p023976 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p023977 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p023978 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p023979 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024030 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024031 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024032 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024033 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024034 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024035 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024036 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024037 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024038 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024039 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024090 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024091 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024092 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024093 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024094 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024095 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024096 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024097 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024098 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024099 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024150 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024151 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024152 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024153 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.61971101475226 | 155.82732252979096 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024154 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024155 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.6197110150467 | 177.07650287476073 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024156 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024157 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.61971101539498 | 212.49180344971188 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| latency_only | v6p024158 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| latency_only | v6p024159 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.61971101567784 | 283.32240459960815 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p023970 | LPDDR5_c8_c2_s8_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 8.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p023971 | LPDDR5_c8_c2_s8_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 8.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024030 | LPDDR5_c8_c2_s16_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 16.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024031 | LPDDR5_c8_c2_s16_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 16.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024090 | LPDDR5_c8_c2_s32_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 32.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024091 | LPDDR5_c8_c2_s32_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 32.0 | 2048.0 | refreshed_median_eligible |
| task_aware | v6p024150 | LPDDR5_c8_c2_s64_p512 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 64.0 | 512.0 | refreshed_median_eligible |
| task_aware | v6p024151 | LPDDR5_c8_c2_s64_p2048 | serial | 2 | 1 | True | 141.6197110145051 | 141.66120229981047 | 2 | 102.4 | 64.0 | 2048.0 | refreshed_median_eligible |

## 4. Secondary Results

16640 strict point-pair/Box memberships analyzed;0 have finite same-type PHY thresholds. Repeated hardware pairs are explicit identity memberships, not independent experiments. Cross-type areas are computed butmarkedcross_type; no single-PHY break-even is invented for them. For identical channel counts common PHY cancels, so no finite PHY threshold exists. MC fixed-pair lower-area fractions and globally reoptimized ranking fractions are distinct model sensitivities.

At central literature coefficients,0/22 Boxes select a strictly lower-area task-aware design. In both main example Boxes, the central minimum-area hardware is the same for latency-only and task-aware; a resource-frontier extension is not evidence of lower total estimated area.

| Lmax_ms | Smax_ms | latency_only_hardware_id | task_aware_hardware_id | area_difference_center_mm2 | MC_fixed_pair_task_lower_fraction | MC_reoptimized_task_lower_fraction | cross_type |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 50 | HBM2_c32_c4_s8_p512 | HBM2_c32_c4_s8_p512 | 0.0 | 0.0 | 0.5785 | False |
| 100 | 75 | HBM2_c16_c3_s8_p512 | HBM2_c16_c3_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 100 | 100 | HBM2_c16_c2_s8_p512 | HBM2_c16_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 150 | 50 | HBM2_c32_c4_s8_p512 | HBM2_c32_c4_s8_p512 | 0.0 | 0.0 | 0.5785 | False |
| 150 | 75 | HBM2_c16_c3_s8_p512 | HBM2_c16_c3_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 150 | 100 | HBM2_c16_c2_s8_p512 | HBM2_c16_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 150 | 150 | HBM2_c8_c2_s8_p512 | HBM2_c8_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 200 | 50 | HBM2_c32_c4_s8_p512 | HBM2_c32_c4_s8_p512 | 0.0 | 0.0 | 0.5785 | False |
| 200 | 75 | HBM2_c16_c3_s8_p512 | HBM2_c16_c3_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 200 | 100 | HBM2_c16_c2_s8_p512 | HBM2_c16_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 200 | 150 | HBM2_c8_c2_s8_p512 | HBM2_c8_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 200 | 200 | HBM2_c8_c1_s8_p512 | HBM2_c8_c1_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 250 | 50 | HBM2_c32_c4_s8_p512 | HBM2_c32_c4_s8_p512 | 0.0 | 0.0 | 0.5785 | False |
| 250 | 75 | HBM2_c16_c3_s8_p512 | HBM2_c16_c3_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 250 | 100 | HBM2_c16_c2_s8_p512 | HBM2_c16_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 250 | 150 | HBM2_c8_c2_s8_p512 | HBM2_c8_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 250 | 200 | HBM2_c8_c1_s8_p512 | HBM2_c8_c1_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 300 | 50 | HBM2_c32_c4_s8_p512 | HBM2_c32_c4_s8_p512 | 0.0 | 0.0 | 0.5785 | False |
| 300 | 75 | HBM2_c16_c3_s8_p512 | HBM2_c16_c3_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 300 | 100 | HBM2_c16_c2_s8_p512 | HBM2_c16_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 300 | 150 | HBM2_c8_c2_s8_p512 | HBM2_c8_c2_s8_p512 | 0.0 | 0.0 | 0.0 | False |
| 300 | 200 | HBM2_c8_c1_s8_p512 | HBM2_c8_c1_s8_p512 | 0.0 | 0.0 | 0.0 | False |

Same-type traffic/MAC comparisons:27; DRAM energy-ratio cancellation checks all passed. F2 uses a common hardware and common allocation across all five k/batching controls. Full-run drain traffic and steady traffic are separately named; primary traffic uses steady bandwidth*period.

## 5. Figure Data

| figure | path | rows |
| --- | --- | --- |
| F1 | paper/figdata/F1_LS_frontiers.csv | 97 |
| F2 | paper/figdata/F2_k_ablation.csv | 15 |
| F3 | paper/figdata/F3_resource_plane.csv | 63666 |
| F3 | paper/figdata/F3_strict_dominance_arrows.csv | 16640 |
| F4 | paper/figdata/F4_best_mapping_grid.csv | 288 |
| F5 | paper/figdata/F5_DRAM_traffic_by_k.csv | 15 |
| F6 | paper/figdata/F6_area_sensitivity.csv | 16640 |

Every CSV starts with a comment recording source path, primary/secondary scope and conditional status. F3 includes every feasible curve identity and separate dominance arrows. Preview:results/v7/paper/preview.png; rough only. Automated nonblank check passed; image viewing was unavailable, so human/visual QA is not claimed. No final styled figures were produced.

## 6. Real-Task Measurement Request

| point_id | hardware_id | mode | k | batching | L_960_ms | S_960_ms | priority | supported_claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v6p007690 | HBM2_c8_c6_s8_p512 | pipelined | 2 | True | 99.68338756519424 | 49.84985585937463 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p007680 | HBM2_c8_c6_s8_p512 | pipelined | 3 | True | 141.67398217586103 | 47.22509473499996 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p012380 | LPDDR5_c16_c8_s8_p512 | pipelined | 2 | True | 92.50660659735226 | 46.29473291015665 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p012330 | LPDDR5_c16_c8_s8_p512 | pipelined | 3 | True | 128.70404950745223 | 42.90789572265635 | 2 | Test a strictly resource-dominating task-aware point in a non-main Box; no success-rate claim yet. |
| v6p016290 | LPDDR5_c32_c2_s8_p512 | serial | 1 | True | 97.35000476461471 | 97.39883512734285 | 2 | Box(200, 100): test latency_only resource alternative (2, 409.6); extension or equality is not strict resource improvement. |
| v6p011000 | LPDDR5_c16_c3_s8_p512 | serial | 1 | True | 85.69691742639829 | 85.71899590820136 | 2 | Box(200, 100): test latency_only resource alternative (3, 204.8); extension or equality is not strict resource improvement. |
| v6p024480 | LPDDR5_c8_c4_s8_p512 | pipelined | 2 | True | 178.1640358159577 | 89.07341015625396 | 2 | Box(200, 100): test task_aware resource alternative (4, 102.4); extension or equality is not strict resource improvement. |
| v6p023970 | LPDDR5_c8_c2_s8_p512 | serial | 1 | True | 141.6197110156709 | 141.66120229980405 | 2 | Box(250, 150): test latency_only resource alternative (2, 102.4); extension or equality is not strict resource improvement. |
| v6p002174 | HBM2_c16_c16_s16_p512 | serial | 1 | True | 24.94786504006622 | 31.20771075195313 | 3 | Low-latency reference near25ms to locate the left boundary of a task-performance plateau. |
| v6p036392 | HBM2_c32_c12_s16_p512 | pipelined | 2 | True | 50.006845438460104 | 21.025479866016013 | 3 | Low-latency reference near50ms to locate the left boundary of a task-performance plateau. |
| v6p014878 | LPDDR5_c32_c16_s16_p512 | pipelined | 2 | True | 74.98727638914691 | 50.00612499999997 | 3 | Low-latency reference near75ms to locate the left boundary of a task-performance plateau. |
| v6p031612 | GDDR6_c24_c12_s16_p512 | pipelined | 3 | True | 95.0305983143513 | 26.81304324562491 | 3 | Low-latency reference near95ms to locate the left boundary of a task-performance plateau. |
| v6p020680 | LPDDR5_c4_c3_s8_p512 | pipelined | 2 | True | 337.6773884905904 | 168.86834008788998 | 4 | Outside-platform counterexample near338/169ms: test whether optimistic platform extrapolation fails. |
| v6p025542 | LPDDR5_c4_c4_s16_p512 | pipelined | 2 | False | 451.4677303908002 | 225.74485965332218 | 4 | Second outside-platform counterexample: task quality must not be inferred from timing alone. |
| v6p026106 | GDDR6_c16_c12_s8_p512 | pipelined | 3 | True | 149.91989180983506 | 56.222044259063026 | 5 | Intermediate latency control to test the shape between low-L references and outside-platform examples. |
| v6p026466 | GDDR6_c16_c12_s16_p512 | pipelined | 3 | True | 149.91989180983506 | 56.222044259063026 | 5 | Intermediate latency control to test the shape between low-L references and outside-platform examples. |

Full protocol:task/measurement_request_v7.md. Four low-L references and two outside-platform counterexamples included. There are no main-Box strict pairs, so none are fabricated; main-Box alternatives are labeled as tradeoffs/equality. Environment/checkpoint/trial/latency/chunk inputs remain null. Both invalid-as-failure and invalid-excluded protocols are mandatory; all-invalid excluded rate is null. Zero episodes executed.

## 7. Limitations

- GDDR6_c16/c24 use conditional NoRefresh and median seq eligibility;small grains do not all pass0.8. This is not physically refreshed GDDR6 validation.
- No new heldout data, no fitting on heldout, no task evaluation and no new cross-host run. Compiled960 checks for nonfrontier F3 points are consistency checks within the frozen model, not independent timing validation.
- All area estimates retain V6 synthesis/extrapolation limitations:no achieved timing/P&R/silicon calibration. Two energy centers are author-supplied vendor claims;LPDDR PHY is a previous-generation proxy.
- Search pruning, discrete SRAM/core choices and five retained period multipliers limit the candidate space; global means minimum among retained discrete candidates, never continuous or exhaustive architecture optimality.
- Empirical quantile scenarios are not probabilities, confidence intervals or closed-loop task robustness.

## 8. Reproduction And Hashes

Inputs:results/v7/inputs/manifest.json. Frozen original V7 spec:results/v7/NEXT_STEPS_V7.md. V6 and earlier deliveries are unchanged; cold evidence remains in verified archives.

```sh
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_prepare.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_sources.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_cost.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_pareto.py pre_recheck
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_finish.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v7_report.py verify
```

Source acquisition failures are retained, not hidden; all derived coefficients are explicitly attributed. Execution logs and copied executed sources:results/v7/execution/. Recheck/stress shards each carry hashes and support exact-input resume. For historical executed code use the matching execution snapshot; do not assume later source edits were the executed revision. delivery_manifest.json hashes all final artifacts except itself, delivery_verification.json and the self-writing08 publication/verification logs, plus current implementation/tests/report. Verify before modifying/rerunning. Existing successful checkpoints are reused, never silently recomputed with different inputs.
