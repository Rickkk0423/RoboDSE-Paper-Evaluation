# CASE V6 Report

Date: 2026-11-16 (America/Los_Angeles).

**Bottom line: B and C are complete. A and D are partially blocked by four unverified external cost coefficients. E is executable preparation, not executed task data. This is NOT a claim that all V6 acceptance goals are satisfied.**

## 1. Gates And Status

| task | status |
| --- | --- |
| A | partial: traceable coefficients/2000-draw propagation; four external coefficients missing |
| B | completed: all frozen frontiers+controls; development-only candidate, no new heldout execution |
| C | completed: three repaired identities/full192-HW DSE; GDDR6_c36 excluded |
| D | partial: global cost selections blocked; all22 boxes, symbolic candidates, conditional comparisons and figures delivered |
| E | prepared_not_executed: conditional point list+six sub100ms; final global selection list awaits cost inputs |

Native audit: 252 successful replays; 30 unsupported aggregate configurations retained. GDDR6_c16 and HBM2_c32 q8192 cross-host controls: all three grains each, counts/cycles/completion times identical (maximum difference0). No specified native-count/traffic/cross-host hard-stop trigger. The finisher DID stop on the derived band L/S audit failure, which was diagnosed and separately rerun as described in Section3. New identities remain independently unvalidated; no heldout data were used to refit the models.

Repaired DSE: 24 memory/core shards, 192 hardware points, 87552 mapping contexts, 188420 curves, 9944 unique/supplement evaluations reopened. 6750 repaired frontier references checked at960 requests; 0 failed steady gates preserved. Paper candidates: 39928.

| memory | status | eta_seq | strict_all_grains_pass |
| --- | --- | --- | --- |
| GDDR6_c16 | accepted_seq_median | 0.872196 | False |
| GDDR6_c24 | accepted_seq_median | 0.800921 | False |
| GDDR6_c36 | excluded_low_seq | 0.787028 | False |
| HBM2_c32 | accepted_seq_median | 0.910627 | True |

Paper primary scope: VLA-layout model, NeuSim unsliced timing, fair allocation, plain layout, sequential-median gate passed. BG/priority/sliced/baseline runs remain separate evidence, not main-paper substitutions. 

## 2. Cost Coefficients

All numerical cost coefficients are **literature_estimate**, never calibrated. Target logic node7nm. Unknown inputs stay null; they are not zero and do not inherit another memory type's values.

| coefficient | mid | low | high | unit | status |
| --- | --- | --- | --- | --- | --- |
| A_core | 6.190084939968001 | 5.043772914048001 | 7.336396965888001 | mm2/core | literature_estimate |
| a_sram | 0.21786335059171597 | 0.1343619078397751 | 0.38353027343750007 | mm2/decimal_MB | literature_estimate |
| A_misc | 1.4526035502958579 | 0.62625 | 3.409583333333334 | mm2/design | literature_estimate |
| e_mac | 0.9214867902869999 | 0.204774842286 | 3.0716226342899997 | pJ/MAC | literature_estimate |
| e_sram | 0.668804462139423 | 0.310516357421875 | 2.484130859375 | pJ/byte | literature_estimate |
| leakage_density | 0.00032171536351165977 | 0.0001407300411522634 | 0.0009708852055072904 | W/mm2 | literature_estimate |
| A_phy_LPDDR5 | None | None | None | mm2/channel | missing_external_input |
| e_dram_LPDDR5 | None | None | None | pJ/bit | missing_external_input |
| A_phy_GDDR6 | None | None | None | mm2/channel | missing_external_input |
| e_dram_GDDR6 | None | None | None | pJ/bit | missing_external_input |
| A_phy_HBM2 | 0.2700073964497041 | 0.2328125 | 0.93125 | mm2/channel | literature_estimate |
| e_dram_HBM2 | 3.92 | 1.96 | 5.955 | pJ/bit | literature_estimate |
| P_static | None | None | None | W/design | derived_per_design_literature_estimate |

Exact primary URLs/DOIs, page/table locations, assumptions and conversions: `results/v6/cost/coefficients.json`. Archived PDFs/extracted text: `cost/sources/`; discovery/access limitations: `cost/sources/discovery/status.json`.

Core: actual Yosys0.71/ABC + official HardFloat + ASAP7 RVT TT predictive libraries. A128x128 BF16-expanded-input/FP32-FMA array is extrapolated from one PE with input/accumulator/output registers and32 FP32 add lanes. Private SRAM counted separately. PE cell area279.5715um2; vector lane148.39524um2. Placement/control factors1.1/1.35/1.6 are declared analyst assumptions. ABC target1GHz; achieved frequency null; no OpenROAD, placement/routing or timing closure performed. Five exact finite PE vectors plus one vector add passed Icarus; not exhaustive arithmetic verification.

MAC energy is an input-capacitance/activity/overhead proxy, not measured switching energy. Internal/glitch/routed clock effects are not separately measured. SRAM density and fixed NoC proxy come from F1 (MICRO2021, commercial14/12nm), geometrically scaled with wide stated uncertainty. F1 Table2 has TWO512GB/s HBM2 PHYs,29.8mm2 combined; no factor-of-two mistake. External HBM2 energy uses Fine-Grained DRAM (MICRO2017) Section2:3.92pJ/bit including ECC, not its0.3pJ/bit I/O-only term; introduction states3.97, included in the envelope. DRAM device energy is not geometrically scaled with7nm logic.

Fixed structure retained: Area=cores*A_core+(shared_MB+cores*private_MB)*a_sram+A_phy(type,channels)+A_misc. Primary energy uses MAC+DRAM only under the specification's missing-SRAM-traffic fallback. SRAM access bytes are not instrumented; e_sram is archived but unused. Area*density*T leakage is supplied separately where full area is available. MACs/request=workload estimated FLOPs/2, not measured retired arithmetic.

All21580 frozen V5.1 attainable rows propagated. 6634 HBM2 rows have full estimated area and6634 have MAC+DRAM energy. LPDDR5/GDDR6 have known-component area only and null total energy. 2000 shared independent-uniform coefficient draws, seed20261116; raw draws archived. Every known coefficient has three low/mid/high scenarios; one-at-a-time plus all-low/mid/high are explicit. Positive linear costs have exact box extrema at low/high corners; a full3^N factorial was not enumerated. Monte Carlo percentiles are conditional model sensitivities, not confidence intervals.

**Global cross-memory minimum-area selection and its ranking fractions are blocked by A_phy_LPDDR5/GDDR6; global energy selection additionally needs e_dram_LPDDR5/GDDR6.** No arbitrary area/energy weights were introduced.

## 3. Empirical Error Bands And Diagnosis

All21580 frozen frontiers plus same-hardware controls: 40594 input rows, 159282 unique480-request runs, 1217820 scenario records,80 audited shards. Only1514 inputs are stable in every stress scenario; 39080 have one or more failed steady gates. `band/intervals.csv` gives finite-stable subset extrema and an explicit unbounded steady-upper flag. Unstable scenarios are not silently dropped to report finite full intervals.

Independent raw L/S reconciliation caught a blank-config-ID engine-cache alias in the initial same-allocation controls. All11200 control inputs were rerun using full semantic keys in `band/control_repair/`; original raw results and `band/initial_summary/` remain untouched as superseded evidence. All21580 frontier inputs have nonblank IDs and were unaffected. Final effective replay count159282; all archived runs including superseded controls170680. `band/intervals.csv` names the actual evidence directory for each input. A blank-ID k1/k2/k3 regression test guards against reintroducing the alias.

Signed e=native_duration/predicted_duration-1; effective bandwidth factor1/(1+e), independently VLM/DiT; aggregate allocations capped at physical peak. Each window quantile is applied globally as a stress, not per-operation locality. W1 lacks DiT observations, so DiT is unchanged and marked unmeasured. Plain/BG residuals pooled within standard/window/stream. Sparse empirical quantiles are not simultaneous bounds, calibrated probabilities, or fresh validation.

| standard | window | stream | n | p5 | p50 | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| GDDR6 | W1 | vlm | 1 | 0.0570695767503564 | 0.0570695767503564 | 0.0570695767503564 |
| GDDR6 | W3 | dit | 1 | -0.3246586426386211 | -0.3246586426386211 | -0.3246586426386211 |
| GDDR6 | W3 | vlm | 1 | -0.3246128826111545 | -0.3246128826111545 | -0.3246128826111545 |
| GDDR6 | W4 | dit | 1 | -0.3466473899678447 | -0.3466473899678447 | -0.3466473899678447 |
| GDDR6 | W4 | vlm | 1 | -0.3466496779695327 | -0.3466496779695327 | -0.3466496779695327 |
| GDDR6 | W5 | dit | 1 | -0.17444900363631888 | -0.17444900363631888 | -0.17444900363631888 |
| GDDR6 | W5 | vlm | 1 | -0.05086148338003893 | -0.05086148338003893 | -0.05086148338003893 |
| HBM2 | W1 | vlm | 2 | -0.027334780883607662 | -0.027250232129164276 | -0.02716568337472089 |
| HBM2 | W3 | dit | 1 | 0.07839468833754215 | 0.07839468833754215 | 0.07839468833754215 |
| HBM2 | W3 | vlm | 1 | 0.07804868875838489 | 0.07804868875838489 | 0.07804868875838489 |
| HBM2 | W4 | dit | 2 | -0.04106931560625215 | -0.029828869880044354 | -0.018588424153836564 |
| HBM2 | W4 | vlm | 2 | -0.04124827162058375 | -0.03304042964618209 | -0.024832587671780433 |
| HBM2 | W5 | dit | 3 | -0.022846109026484283 | 0.055864953082075175 | 0.1506917512015416 |
| HBM2 | W5 | vlm | 3 | -0.017692271988541553 | -0.0169682944244961 | 0.17681363354545154 |
| LPDDR5 | W1 | vlm | 2 | -0.01117548066184738 | -0.00530523203119293 | 0.0005650165994615202 |
| LPDDR5 | W3 | dit | 1 | -0.1336854311907807 | -0.1336854311907807 | -0.1336854311907807 |
| LPDDR5 | W3 | vlm | 1 | -0.1336954311858034 | -0.1336954311858034 | -0.1336954311858034 |
| LPDDR5 | W4 | dit | 2 | -0.09049224143014471 | -0.053968358276522965 | -0.017444475122901225 |
| LPDDR5 | W4 | vlm | 2 | -0.09043074146055868 | -0.053938358289491506 | -0.01744597511842433 |
| LPDDR5 | W5 | dit | 3 | -0.002713370071269851 | 0.28167651065300414 | 0.47529550087819566 |
| LPDDR5 | W5 | vlm | 3 | -0.009413448270835723 | 0.09953187768086579 | 0.20310318022690707 |

Development-only proportional frontend rule: all six standard/layout groups have maximum absolute error<=5%; new heldout specification draft frozen, not executed. Whole-trace byte weights require finite-window lookahead and are not an online deployable scheduler. W3/W4 development windows are contiguous; there is no matched full-address W5 counterfactual, so arbitration vs W5 locality cannot be uniquely separated. Existing sampling controls do not constitute an independent W5 model validation.

| group | rule | flows | mean_error_pct | max_error_pct | all_le_5pct |
| --- | --- | --- | --- | --- | --- |
| GDDR6_bg | original_fair | 8 | 22.922842802011502 | 29.080233785594835 | False |
| GDDR6_bg | frontend_proportional | 8 | 1.3881721679011165 | 1.407586288533369 | True |
| GDDR6_plain | original_fair | 8 | 18.376863333497816 | 25.7926025448562 | False |
| GDDR6_plain | frontend_proportional | 8 | 1.2668574056282607 | 1.2864882755883378 | True |
| HBM2_bg | original_fair | 6 | 0.7804310886895705 | 0.7925449325519196 | True |
| HBM2_bg | frontend_proportional | 6 | 0.008758976595796275 | 0.008759743827491118 | True |
| HBM2_plain | original_fair | 12 | 2.319288865474148 | 3.206604698424531 | True |
| HBM2_plain | frontend_proportional | 12 | 1.7099822100979525 | 2.3017092435000164 | True |
| LPDDR5_bg | original_fair | 10 | 1.627821530166256 | 2.0012806159521723 | True |
| LPDDR5_bg | frontend_proportional | 10 | 1.6278215284999231 | 2.001280625203461 | True |
| LPDDR5_plain | original_fair | 4 | 0.004376839105740826 | 0.004377030656821379 | True |
| LPDDR5_plain | frontend_proportional | 4 | 0.004376839105746377 | 0.004377030656788072 | True |

Candidate: `diagnosis/next_heldout_spec_draft.json`; fit provenance and limitations: `diagnosis/status.json`. No development rule was substituted into primary DSE parameters.

## 4. High-Bandwidth Repair

Full100 identities and every grain: `seq_comparison.csv`. Raw-address mappers: MOP4CLXOR,ChRaBaRoCo,RoBaRaCoCh, RITAddrMapper(MOP,0 reserved rows). PassThroughMapper needs decoded addr_vec and is not a raw-address frontend option. NoRefresh, explicit PerBank/AllBank variants were tested for GDDR6. The pinned GenericDDR has no implicit refresh default; refresh variants are not relabeled as an unspecified default.

| memory | mapper | refresh | mode | outstanding | grains |
| --- | --- | --- | --- | --- | --- |
| GDDR6_c16 | MOP4CLXOR | NoRefresh | aggregate | 8192 | 0.700160, 0.872196, 0.879791 |
| GDDR6_c24 | MOP4CLXOR | NoRefresh | independent | 8192 | 0.750671, 0.800921, 0.876446 |
| GDDR6_c36 | MOP4CLXOR | NoRefresh | independent | 8192 | 0.693074, 0.787028, 0.879945 |
| HBM2_c32 | MOP4CLXOR | HBMPerBankRefresh | aggregate | 8192 | 0.910627, 0.930275, 0.909010 |

Gate deliberately follows frozen V5.1 eta_seq=median of the same three granularities. Stricter all-grain gate is separately reported: accepted GDDR6_c16/c24 still fail the small-grain0.8 threshold. GDDR6_c36 best median0.787028 remains excluded_low_seq. GDDR6_c16/c24 NoRefresh acceptance is conditional, not a validated physical refreshed device.

GDDR6_c16 PerBank q8192 also exceeds0.8 by the median gate (about0.8497), but the frozen selection policy maximizes the median and therefore selected NoRefresh0.8722. This is a policy choice, not evidence that physical refresh cannot pass. Complete refresh/mapper medians and unsupported aggregate controls are separately tabulated.

HBM2_c32 WAS ALREADY one aggregate32-channel native handle in V5.1, not stitched. Raising outstanding512->8192 improves median0.543885->0.910627; aggregate and independent sequence results match. This supports a frontend-window limitation in the tested case rather than the assumed stitching cause. GDDR6 non-power-of-two aggregate24/36 was genuinely constructed and rejected by the pinned power-of-two mapper; timings are unsupported, not successful equivalence. All failed/unsupported groups are preserved.

Each of three accepted identities reran12 original64MiB VLA/legacy plain/BG mix traces at25/50/75 ratios and two W5 controls. Calibration fit is development data only. W5 sampling controls adopt c16L2/c24L1/HBM32L2; this verifies the sampling protocol, not the new absolute timing model. Repaired DSE uses the identical frozen V5.1 search/grid/kernel/provider with only the three memory calibrations changed. Search failures/pruning and all raw traces retained.

## 5. Selection Comparisons

**The literal Box grid has22 combinations (3+4+5+5+5), not23.** Every Box has a row in `paper/selection_comparison.csv`; global selected hardware/mapping/cost/robustness fields are null with explicit BLOCKED status. Counts of globally identical selections, globally cheaper Boxes, bandwidth/core/cost-ratio distributions and global robust fractions are therefore **unavailable**, not zero.

Conditional within-memory area comparisons: 198 rows across nine eligible memory tiers, 156 reachable pairs, 151 identical point pairs, 5 nominally lower-area task-aware pairs; 0 of those remain jointly feasible in every matched stress scenario. These are Box x memory-tier counts, NOT global Box counts. Same-tier PHY cancels exactly; common A_misc cancels; 2000 shared coefficient draws assess fixed nominal pair area ranking. Total intervals stay null where PHY is unknown.

The5 cheaper conditional rows represent1 distinct hardware/mapping pair(s), not independent discoveries. Their cost and timing robustness are different questions:

| Lmax_ms | Smax_ms | memory | serial_hardware_id | task_hardware_id | area_difference_value_mm2 | MC_task_area_lower_fraction | error_band_robust_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 50 | HBM2_c8 | HBM2_c8_c8_s8_p512 | HBM2_c8_c6_s8_p512 | -12.608616160646061 | 1.0 | 0.4666666666666667 |
| 150 | 50 | HBM2_c8 | HBM2_c8_c8_s8_p512 | HBM2_c8_c6_s8_p512 | -12.608616160646061 | 1.0 | 0.4666666666666667 |
| 200 | 50 | HBM2_c8 | HBM2_c8_c8_s8_p512 | HBM2_c8_c6_s8_p512 | -12.608616160646061 | 1.0 | 0.4666666666666667 |
| 250 | 50 | HBM2_c8 | HBM2_c8_c8_s8_p512 | HBM2_c8_c6_s8_p512 | -12.608616160646061 | 1.0 | 0.4666666666666667 |
| 300 | 50 | HBM2_c8 | HBM2_c8_c8_s8_p512 | HBM2_c8_c6_s8_p512 | -12.608616160646061 | 1.0 | 0.4666666666666667 |

Final conditional area selections: 33 unique points independently rechecked at960 requests, max timestamp difference0s, final rejected points0. Targeted empirical stresses: 990 runs, 647 stable. New frontend identities transfer OLD heldout residuals and are explicitly unvalidated. Robust fractions count matched quantile-rank scenarios; no probability interpretation or per-scenario global reoptimization.

Latency-only serial candidates use their minimum stable launch period, not arbitrarily slow serial curve points. The literal test is L<=Smax; actual simulated S is reported, with up to search resolution separation from L. Task-aware search includes serial and k1/2/3 batched/unbatched retained curves, plus required unbatched controls. Original LB>1.2*incumbent pruning remains; only five discrete launch factors are searched. No continuous/global optimum claim.

Private512/2048KiB capacities retain separate area identities but exactly reuse timing under the frozen provider's feasibility-only private-SRAM semantics. The sweep does not establish a calibrated private-cache timing benefit.

Parametric cross-bandwidth illustrations: `paper/parametric_bandwidth_pairs.csv`. These minimize bandwidth first, then known area, NOT total area. They expose exact area difference = known difference + delta_channels*A_phy(type), with2000-draw break-even threshold quantiles instead of invented PHY numbers. `paper/energy_selection_HBM2_only.csv` separately minimizes known MAC+DRAM energy within HBM2 only; it is not a global energy optimum and not every energy-subset point has a dedicated960-request check.

For Box(200,100)ms, the bandwidth-minimizing LPDDR illustration is LPDDR5_c16_c3_s8_p512 serial at L/S=85.697/85.719ms versus LPDDR5_c8_c4_s8_p512 k=2 batched at 178.164/89.073ms. Bandwidth ratio0.5; one extra core adds6.304mm2 of known estimated area and saves eight PHY channels. Task-aware area is lower only if LPDDR5 PHY area exceeds0.788mm2/channel at central coefficients (threshold MC p5/p95=0.661/0.920). The missing PHY input prevents deciding that inequality; this is NOT evidence that bandwidth halving necessarily reduces chip area.

## 6. Paper Data And Figures

| file | purpose |
| --- | --- |
| selection_comparison.csv | 22 Box rows; explicit global-cost blocker |
| selection_comparison_within_memory.csv | Same-tier conditional area MC and empirical stresses |
| symbolic_cost_candidates.csv | Positive-resource-undominated alternatives with symbolic PHY term |
| parametric_bandwidth_pairs.csv | Cross-bandwidth symbolic PHY break-even sensitivity |
| energy_selection_HBM2_only.csv | Separate energy objective on known HBM2 subset |
| candidate_points.csv | All retained primary curves incl unbatched/controls; provenance preserved |
| k_ablation_summary.csv | Four representative HW, LPDDR102.4GB/s4/8 cores mandatory; all five same-split controls |
| seq_mapper_refresh_summary.csv | All100 mapper/refresh/front-end identities with median/min/max gates |
| native_instance_controls.csv | MOP aggregate/independent and outstanding512/8192 controls, unsupported cases retained |
| frontier_by_memory.csv | One retained L/S frontier per eligible memory tier |
| when_batching_selected.csv | Fixed-HW lowest-L mapping at S targets; descriptive reasons, not causal proof |
| selected_rechecks/ | 960-request original vs compiled request evidence |
| selected_stress/ | All raw fixed-period empirical stress timestamps |
| figures/ | Three PNG scientific plots; pixel/nonblank/text-bounds QA, no human visual inspection |

All listed files are under `results/v6/paper/`. k controls retain DiT GB/request, busy fractions, Tmin/L/S, compute/exposed-memory/linear/attention/wait round components; the same allocation is used within each hardware. Traffic conservation and both time decompositions were independently audited in every repaired evaluation.

## 7. Task Measurement Request

`task/measurement_request.md`: 34 unique proposed L/S points, including six additional distinct L<100ms points. The list covers conditional per-memory area selections, NOT finalized global-cost choices. Closed-loop task episodes added: **0**. Checkpoint, environment, speed bands, budget, success/invalid criteria, injection implementation and chunk adoption are external inputs left null. No synthetic outcomes/checkpoints.

Each point/speed must report trials/successes/invalid separately. Mandatory invalid-as-failure K/N and invalid-excluded K/(N-I) summaries; all-invalid excluded rate is null. `v6_task.py validate` validates genuine supplied counts and metadata, never launches an environment or produces successes. The blank results template intentionally fails validation.

## 8. Failures, Limits And Reproduction

Input specification provenance: `results/v6/NEXT_STEPS_V6_READBACK.md`; origin=full_tool_readback_reconstruction. The original Downloads path was fully read at the start but had disappeared by publication. The explicitly marked tool-readback reconstruction preserves the executed requirements; byte identity to the unavailable original cannot be verified. No Downloads files were restored or modified. See `input_spec_provenance.json`.

Preserved failures: local seq collector initially called digest on str instead of Path; valid completed raw native results and failure.json retained, corrected successful local run separate. Initial synthesis library filename/metadata handling failures preserved in prior logs. Initial seq preparation assumed a per-item seq field instead of the actual global seq_traces; fixed before the frozen input manifest. Known implementation errors: `execution/implementation_failures.json`. Wrong F1 venue URL404 corrected via author page. Initial band control-cache alias was detected by independent raw L/S reconstruction; all affected controls were rerun in a separate frozen source/output identity, not silently repaired in place. Plot QA initially included a nonrendered out-of-view tick; corrected to inspect actual in-view tick labels. Executed collector/plot/finisher sources before these presentation changes are archived in finish/attempt_1; resume dependencies pin the previously completed numeric audits and stage tests. Rambus guessed PDFs404 and landing page redirects to login; IEEE/ACM retrieval did not yield verified numeric inputs. Correct NVIDIA source found through public publications search, no access controls bypassed. See `cost/sources/discovery/status.json` and `execution/` for limitations, Slurm IDs2050674/2051916 and accounting.

Uncovered/degraded: four cost coefficients; no SRAM access-byte counter; no routed/clock-tree/internal switching power; no physical timing closure; no fresh heldout execution; W5 causal decomposition unresolved; NoRefresh GDDR acceptance; unsupported nonpower aggregate mapper; heuristic optimization pruning; empirical stresses are not confidence limits; HBM2 energy-subset choices not all960 rechecked; conditional task list not finalized global-cost list. These limit paper claims and are not silently marked complete.

| file | tests | failures |
| --- | --- | --- |
| final.xml | 318 | 0 |
| stage_A_cost.xml | 311 | 0 |
| stage_B_aggregate.xml | 306 | 0 |
| stage_B_control_repair_C_DSE.xml | 317 | 0 |
| stage_B_diagnosis.xml | 306 | 0 |
| stage_B_implementation.xml | 304 | 0 |
| stage_C_native.xml | 306 | 0 |
| stage_D_E_implementation.xml | 314 | 0 |
| stage_D_E_tooling.xml | 315 | 0 |
| stage_D_paper.xml | 317 | 0 |
| stage_E_task.xml | 317 | 0 |

Reproduction (all run from repository root; existing stages resume by checkpoint):

```sh
# Input preparation is one-shot; skip when frozen manifests already exist.
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_prepare.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_remote.py seq
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py select
# prepare is one-shot; reuse frozen repair_input/manifest.json on resume
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_remote.py repair
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py collect
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py dse --workers 4
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_band.py run --workers 4
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_control_band.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_audit.py band
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_arbiter.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_finish.py
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_report.py verify
```

Synthesis reproduction: official HardFloat source and exact Liberty files are archived under cost/synth; `PYTHONPATH=vlasim .venv/bin/python vlasim/v6_synth.py`, then `v6_rtl_check.py`. Optional tool versions and source hashes are archived; no dependency metadata churn in the existing repo.

Preservation: V5.1 80924 artifacts and23 source/report hashes unchanged; earlier deliveries1506 artifacts unchanged. Final V6 artifacts, source files, input specification and this report are SHA256-pinned in `results/v6/delivery_manifest.json`. Verification record is deliberately outside its own manifest; it pins the manifest hash and does not create a recursive hash dependency.

External unblock request: `cost/external_input_request.json`. Supply traceable per-type PHY area and DRAM+I/O energy with width/rate/node/voltage/scope and uncertainty. Then fill the coefficients, rerun global cost optimization and selected-point stresses, regenerate the task list. Existing native/DSE/error-band evidence does not need to be fabricated or discarded.
