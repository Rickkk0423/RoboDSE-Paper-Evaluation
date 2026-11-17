"""Publish a candid eight-section V6 report and independently verifiable delivery."""
import argparse
from collections import Counter
from pathlib import Path
import platform
import shutil
import sys
import xml.etree.ElementTree as ET

import numpy as np

from v6_common import ROOT,OLD,load,write_json,digest,preserve
from v51_package import read_csv


def table(rows,keys):
    return ['| '+' | '.join(keys)+' |','| '+' | '.join('---' for _ in keys)+' |',
        *['| '+' | '.join(str(r.get(k,'')) for k in keys)+' |' for r in rows]]


def earlier():
    results=[]
    for path in (Path('results/case_v3_complete/delivery_manifest.json'),Path('results/v4/delivery_manifest.json'),Path('results/v5/delivery_manifest.json')):
        m=load(path)
        files={Path(name):sha for name,sha in m['files'].items()} if 'files' in m else {path.parent/name:sha for name,sha in m['artifacts_sha256'].items()}
        changed=[str(name) for name,sha in files.items() if not name.is_file() or digest(name)!=sha]
        sources=m.get('implementation_sha256',m.get('source_sha256',{}))
        if isinstance(sources,dict):changed.extend(name for name,sha in sources.items() if digest(name)!=sha)
        if m.get('report_sha256'):
            report=Path('docs/CASE_V4_RESULTS.md' if path.parent.name=='v4' else 'docs/CASE_V5_REPORT.md')
            if digest(report)!=m['report_sha256']:changed.append(str(report))
        if changed:raise RuntimeError('HARD_STOP_prior_delivery_changed '+str(changed))
        results.append(dict(manifest=str(path),artifacts=len(files),passed=True))
    return results


def archive_spec(original='/Users/mr.meeseeks/Downloads/NEXT_STEPS_V6.md'):
    source=Path(original)
    if source.exists():
        target=ROOT/'NEXT_STEPS_V6.md';shutil.copy2(source,target)
        metadata=dict(origin='original_file_copy',source=str(source),source_available=True,
            byte_identity_to_original=True,archived=str(target),sha256=digest(target))
    else:
        target=ROOT/'NEXT_STEPS_V6_READBACK.md'
        if not target.exists():raise RuntimeError('Original specification missing; an explicitly attributed readback is required')
        metadata=dict(origin='full_tool_readback_reconstruction',source=str(source),source_available=False,
            byte_identity_to_original=None,archived=str(target),sha256=digest(target),
            limitation='Original was fully read before execution but no longer exists at publication; '
                'readback is NOT a verified byte-identical original. Downloads was not restored or modified.')
    write_json(ROOT/'input_spec_provenance.json',metadata)
    return metadata


def publish():
    preserved=dict(v5_1=preserve(),earlier=earlier());write_json(ROOT/'validation/final_preservation.json',preserved)
    input_spec=archive_spec()
    c=load(ROOT/'cost/coefficients.json');cost=load(ROOT/'cost/status.json');band=load(ROOT/'band/audit.json')
    native=load(ROOT/'validation/native_audit.json');dse=load(ROOT/'validation/dse_archive_audit.json')
    selection=load(ROOT/'paper/selection_status.json');col=load(ROOT/'paper/collection.json');task=load(ROOT/'task/status.json')
    stress=load(ROOT/'paper/selected_stress_status.json');refs=load(ROOT/'paper/selected_recheck_status.json')
    tiers=load(ROOT/'repair_selection.json')['tiers'];controls=read_csv(ROOT/'paper/k_ablation_summary.csv')
    cond=read_csv(ROOT/'paper/selection_comparison_within_memory.csv');pairs=[r for r in cond if r.get('serial_point_id') and r.get('task_point_id')]
    same=sum(r.get('same_design')=='True' for r in pairs)
    cheap=[r for r in pairs if float(r['area_difference_value_mm2'])<-1e-12]
    robust=[r for r in cheap if float(r.get('error_band_robust_fraction') or 0)==1.]
    example=next(r for r in read_csv(ROOT/'paper/parametric_bandwidth_pairs.csv') if r['Lmax_ms']=='200' and r['Smax_ms']=='100' and r['standard']=='LPDDR5')
    tests=[]
    for path in sorted((ROOT/'validation').glob('*.xml')):
        root=ET.parse(path).getroot();suites=list(root.iter('testsuite'))
        tests.append(dict(file=path.name,tests=sum(int(s.get('tests',0)) for s in suites),
            failures=sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)))
    if any(r['failures'] for r in tests):raise RuntimeError('Cannot publish failed test stage')
    if any(not s['passed'] for s in (band,native,dse)) or task['task_episodes_run']!=0:
        raise RuntimeError('Cannot publish failed audit/unexpected task data')
    status=dict(status='completed_feasible_work_with_external_cost_blockers',
        A='partial: traceable coefficients/2000-draw propagation; four external coefficients missing',
        B='completed: all frozen frontiers+controls; development-only candidate, no new heldout execution',
        C='completed: three repaired identities/full192-HW DSE; GDDR6_c36 excluded',
        D='partial: global cost selections blocked; all22 boxes, symbolic candidates, conditional comparisons and figures delivered',
        E='prepared_not_executed: conditional point list+six sub100ms; final global selection list awaits cost inputs',
        specified_native_traffic_crosshost_hard_stop=False,finisher_audit_stop_occurred=True,
        implementation_band_audit_failure_repaired=True,
        input_spec_origin=input_spec['origin'],
        independent_model_validation='NOT_PASSED',task_episodes_run=0,
        blocked_inputs=c['blocked_inputs'])
    write_json(ROOT/'status.json',status)
    lines=['# CASE V6 Report', '', 'Date: 2026-11-16 (America/Los_Angeles).', '',
        '**Bottom line: B and C are complete. A and D are partially blocked by four unverified external cost coefficients. '
        'E is executable preparation, not executed task data. This is NOT a claim that all V6 acceptance goals are satisfied.**', '',
        '## 1. Gates And Status', '',
        *table([dict(task=k,status=status[k]) for k in ('A','B','C','D','E')],['task','status']), '',
        f'Native audit: {native["completed"]} successful replays; {native["rows"]-native["completed"]} unsupported aggregate configurations retained. '
        'GDDR6_c16 and HBM2_c32 q8192 cross-host controls: all three grains each, counts/cycles/completion times identical (maximum difference0). '
        'No specified native-count/traffic/cross-host hard-stop trigger. The finisher DID stop on the derived band L/S audit '
        'failure, which was diagnosed and separately rerun as described in Section3. New identities remain independently '
        'unvalidated; no heldout data were used to refit the models.', '',
        f'Repaired DSE: {col["completed_shards"]} memory/core shards, {col["repaired_hardware_points"]} hardware points, '
        f'{col["repaired_context_rows"]} mapping contexts, {col["repaired_curve_rows"]} curves, {dse["evaluations"]} unique/supplement evaluations reopened. '
        f'{col["reference_frontiers"]} repaired frontier references checked at960 requests; '
        f'{col["reference_failed"]} failed steady gates preserved. Paper candidates: {col["candidate_points"]}.', '',
        *table([dict(memory=m,status=v['status'],eta_seq=round(v['eta_seq'],6),strict_all_grains_pass=v['strict_all_grains_pass']) for m,v in tiers.items()],
            ['memory','status','eta_seq','strict_all_grains_pass']), '',
        'Paper primary scope: VLA-layout model, NeuSim unsliced timing, fair allocation, plain layout, sequential-median gate passed. '
        'BG/priority/sliced/baseline runs remain separate evidence, not main-paper substitutions. ', '',
        '## 2. Cost Coefficients', '',
        'All numerical cost coefficients are **literature_estimate**, never calibrated. Target logic node7nm. '
        'Unknown inputs stay null; they are not zero and do not inherit another memory type\'s values.', '',
        *table([dict(coefficient=k,mid=v['value'],low=v['lower'],high=v['upper'],unit=v['unit'],status=v['status']) for k,v in c['coefficients'].items()],
            ['coefficient','mid','low','high','unit','status']), '',
        'Exact primary URLs/DOIs, page/table locations, assumptions and conversions: `results/v6/cost/coefficients.json`. '
        'Archived PDFs/extracted text: `cost/sources/`; discovery/access limitations: `cost/sources/discovery/status.json`.', '',
        'Core: actual Yosys0.71/ABC + official HardFloat + ASAP7 RVT TT predictive libraries. A128x128 BF16-expanded-input/FP32-FMA array '
        'is extrapolated from one PE with input/accumulator/output registers and32 FP32 add lanes. Private SRAM counted separately. '
        'PE cell area279.5715um2; vector lane148.39524um2. Placement/control factors1.1/1.35/1.6 are declared analyst assumptions. '
        'ABC target1GHz; achieved frequency null; no OpenROAD, placement/routing or timing closure performed. '
        'Five exact finite PE vectors plus one vector add passed Icarus; not exhaustive arithmetic verification.', '',
        'MAC energy is an input-capacitance/activity/overhead proxy, not measured switching energy. Internal/glitch/routed clock effects '
        'are not separately measured. SRAM density and fixed NoC proxy come from F1 (MICRO2021, commercial14/12nm), geometrically scaled '
        'with wide stated uncertainty. F1 Table2 has TWO512GB/s HBM2 PHYs,29.8mm2 combined; no factor-of-two mistake. '
        'External HBM2 energy uses Fine-Grained DRAM (MICRO2017) Section2:3.92pJ/bit including ECC, not its0.3pJ/bit I/O-only term; '
        'introduction states3.97, included in the envelope. DRAM device energy is not geometrically scaled with7nm logic.', '',
        'Fixed structure retained: Area=cores*A_core+(shared_MB+cores*private_MB)*a_sram+A_phy(type,channels)+A_misc. '
        'Primary energy uses MAC+DRAM only under the specification\'s missing-SRAM-traffic fallback. SRAM access bytes are not instrumented; '
        'e_sram is archived but unused. Area*density*T leakage is supplied separately where full area is available. '
        'MACs/request=workload estimated FLOPs/2, not measured retired arithmetic.', '',
        f'All{cost["frontier_rows"]} frozen V5.1 attainable rows propagated. {cost["area_complete_rows"]} HBM2 rows have full estimated '
        f'area and{cost["energy_complete_rows"]} have MAC+DRAM energy. LPDDR5/GDDR6 have known-component area only and null total energy. '
        '2000 shared independent-uniform coefficient draws, seed20261116; raw draws archived. Every known coefficient has three '
        'low/mid/high scenarios; one-at-a-time plus all-low/mid/high are explicit. Positive linear costs have exact box extrema at '
        'low/high corners; a full3^N factorial was not enumerated. Monte Carlo percentiles are conditional model sensitivities, not confidence intervals.', '',
        '**Global cross-memory minimum-area selection and its ranking fractions are blocked by A_phy_LPDDR5/GDDR6; '
        'global energy selection additionally needs e_dram_LPDDR5/GDDR6.** No arbitrary area/energy weights were introduced.', '',
        '## 3. Empirical Error Bands And Diagnosis', '',
        f'All{band["frontier_inputs"]} frozen frontiers plus same-hardware controls: {band["input_rows"]} input rows, '
        f'{band["unique_runs"]} unique480-request runs, {band["scenario_rows"]} scenario records,80 audited shards. '
        f'Only{band["fully_stable_inputs"]} inputs are stable in every stress scenario; '
        f'{band["partially_or_fully_unstable_inputs"]} have one or more failed steady gates. '
        '`band/intervals.csv` gives finite-stable subset extrema and an explicit unbounded steady-upper flag. '
        'Unstable scenarios are not silently dropped to report finite full intervals.', '',
        f'Independent raw L/S reconciliation caught a blank-config-ID engine-cache alias in the initial same-allocation controls. '
        f'All11200 control inputs were rerun using full semantic keys in `band/control_repair/`; original raw results and '
        f'`band/initial_summary/` remain untouched as superseded evidence. All21580 frontier inputs have nonblank IDs and were '
        f'unaffected. Final effective replay count{band["unique_runs"]}; all archived runs including superseded controls'
        f'{band["archived_runs_including_superseded"]}. `band/intervals.csv` names the actual evidence directory for each input. '
        'A blank-ID k1/k2/k3 regression test guards against reintroducing the alias.', '',
        'Signed e=native_duration/predicted_duration-1; effective bandwidth factor1/(1+e), independently VLM/DiT; '
        'aggregate allocations capped at physical peak. Each window quantile is applied globally as a stress, not per-operation locality. '
        'W1 lacks DiT observations, so DiT is unchanged and marked unmeasured. Plain/BG residuals pooled within standard/window/stream. '
        'Sparse empirical quantiles are not simultaneous bounds, calibrated probabilities, or fresh validation.', '',
        *table(read_csv(ROOT/'band/quantiles.csv'),['standard','window','stream','n','p5','p50','p95']), '',
        'Development-only proportional frontend rule: all six standard/layout groups have maximum absolute error<=5%; '
        'new heldout specification draft frozen, not executed. Whole-trace byte weights require finite-window lookahead and are '
        'not an online deployable scheduler. W3/W4 development windows are contiguous; there is no matched full-address W5 '
        'counterfactual, so arbitration vs W5 locality cannot be uniquely separated. Existing sampling controls do not constitute '
        'an independent W5 model validation.', '',
        *table(read_csv(ROOT/'diagnosis/development_summary.csv'),list(read_csv(ROOT/'diagnosis/development_summary.csv')[0])), '',
        'Candidate: `diagnosis/next_heldout_spec_draft.json`; fit provenance and limitations: `diagnosis/status.json`. '
        'No development rule was substituted into primary DSE parameters.', '',
        '## 4. High-Bandwidth Repair', '',
        'Full100 identities and every grain: `seq_comparison.csv`. Raw-address mappers: MOP4CLXOR,ChRaBaRoCo,RoBaRaCoCh, '
        'RITAddrMapper(MOP,0 reserved rows). PassThroughMapper needs decoded addr_vec and is not a raw-address frontend option. '
        'NoRefresh, explicit PerBank/AllBank variants were tested for GDDR6. The pinned GenericDDR has no implicit refresh default; '
        'refresh variants are not relabeled as an unspecified default.', '',
        *table([dict(memory=m,mapper=v['item']['mapper'],refresh=v['item']['config']['refresh'],mode=v['item']['mode'],
            outstanding=v['item']['outstanding'],grains=', '.join(f'{x:.6f}' for x in v['seq_three_grains'])) for m,v in tiers.items()],
            ['memory','mapper','refresh','mode','outstanding','grains']), '',
        'Gate deliberately follows frozen V5.1 eta_seq=median of the same three granularities. Stricter all-grain gate is separately '
        'reported: accepted GDDR6_c16/c24 still fail the small-grain0.8 threshold. GDDR6_c36 best median0.787028 remains excluded_low_seq. '
        'GDDR6_c16/c24 NoRefresh acceptance is conditional, not a validated physical refreshed device.', '',
        'GDDR6_c16 PerBank q8192 also exceeds0.8 by the median gate (about0.8497), but the frozen selection policy '
        'maximizes the median and therefore selected NoRefresh0.8722. This is a policy choice, not evidence that physical '
        'refresh cannot pass. Complete refresh/mapper medians and unsupported aggregate controls are separately tabulated.', '',
        'HBM2_c32 WAS ALREADY one aggregate32-channel native handle in V5.1, not stitched. Raising outstanding512->8192 improves '
        'median0.543885->0.910627; aggregate and independent sequence results match. This supports a frontend-window limitation '
        'in the tested case rather than the assumed stitching cause. GDDR6 non-power-of-two aggregate24/36 was genuinely constructed '
        'and rejected by the pinned power-of-two mapper; timings are unsupported, not successful equivalence. '
        'All failed/unsupported groups are preserved.', '',
        'Each of three accepted identities reran12 original64MiB VLA/legacy plain/BG mix traces at25/50/75 ratios and two W5 controls. '
        'Calibration fit is development data only. W5 sampling controls adopt c16L2/c24L1/HBM32L2; this verifies the sampling protocol, '
        'not the new absolute timing model. Repaired DSE uses the identical frozen V5.1 search/grid/kernel/provider with only the '
        'three memory calibrations changed. Search failures/pruning and all raw traces retained.', '',
        '## 5. Selection Comparisons', '',
        '**The literal Box grid has22 combinations (3+4+5+5+5), not23.** '
        'Every Box has a row in `paper/selection_comparison.csv`; global selected hardware/mapping/cost/robustness fields are null '
        'with explicit BLOCKED status. Counts of globally identical selections, globally cheaper Boxes, bandwidth/core/cost-ratio '
        'distributions and global robust fractions are therefore **unavailable**, not zero.', '',
        f'Conditional within-memory area comparisons: {len(cond)} rows across nine eligible memory tiers, {len(pairs)} reachable '
        f'pairs, {same} identical point pairs, {len(cheap)} nominally lower-area task-aware pairs; '
        f'{len(robust)} of those remain jointly feasible in every matched stress scenario. '
        'These are Box x memory-tier counts, NOT global Box counts. Same-tier PHY cancels exactly; common A_misc cancels; '
        '2000 shared coefficient draws assess fixed nominal pair area ranking. Total intervals stay null where PHY is unknown.', '',
        f'The{len(cheap)} cheaper conditional rows represent{len({(r["serial_point_id"],r["task_point_id"]) for r in cheap})} distinct hardware/mapping pair(s), '
        'not independent discoveries. Their cost and timing robustness are different questions:', '',
        *table(cheap,['Lmax_ms','Smax_ms','memory','serial_hardware_id','task_hardware_id','area_difference_value_mm2',
            'MC_task_area_lower_fraction','error_band_robust_fraction']), '',
        f'Final conditional area selections: {refs["points"]} unique points independently rechecked at960 requests, '
        f'max timestamp difference{refs["max_absolute_error_s"]:.3g}s, final rejected points{len(refs["failed"])}. '
        f'Targeted empirical stresses: {stress["runs"]} runs, {stress["stable_runs"]} stable. '
        'New frontend identities transfer OLD heldout residuals and are explicitly unvalidated. Robust fractions count matched '
        'quantile-rank scenarios; no probability interpretation or per-scenario global reoptimization.', '',
        'Latency-only serial candidates use their minimum stable launch period, not arbitrarily slow serial curve points. '
        'The literal test is L<=Smax; actual simulated S is reported, with up to search resolution separation from L. '
        'Task-aware search includes serial and k1/2/3 batched/unbatched retained curves, plus required unbatched controls. '
        'Original LB>1.2*incumbent pruning remains; only five discrete launch factors are searched. No continuous/global optimum claim.', '',
        'Private512/2048KiB capacities retain separate area identities but exactly reuse timing under the frozen provider\'s '
        'feasibility-only private-SRAM semantics. The sweep does not establish a calibrated private-cache timing benefit.', '',
        'Parametric cross-bandwidth illustrations: `paper/parametric_bandwidth_pairs.csv`. These minimize bandwidth first, '
        'then known area, NOT total area. They expose exact area difference = known difference + delta_channels*A_phy(type), '
        'with2000-draw break-even threshold quantiles instead of invented PHY numbers. '
        '`paper/energy_selection_HBM2_only.csv` separately minimizes known MAC+DRAM energy within HBM2 only; '
        'it is not a global energy optimum and not every energy-subset point has a dedicated960-request check.', '',
        f'For Box(200,100)ms, the bandwidth-minimizing LPDDR illustration is '
        f'{example["serial_hardware"]} serial at L/S={float(example["serial_L_ms"]):.3f}/{float(example["serial_S_ms"]):.3f}ms versus '
        f'{example["task_hardware"]} k={example["task_k"]} batched at '
        f'{float(example["task_L_ms"]):.3f}/{float(example["task_S_ms"]):.3f}ms. Bandwidth ratio{example["bandwidth_ratio"]}; '
        f'one extra core adds{float(example["area_difference_known_mid_mm2"]):.3f}mm2 of known estimated area and saves eight PHY channels. '
        f'Task-aware area is lower only if LPDDR5 PHY area exceeds{float(example["phy_break_even_mid_mm2_per_channel"]):.3f}mm2/channel '
        f'at central coefficients (threshold MC p5/p95={float(example["phy_break_even_MC_p5"]):.3f}/'
        f'{float(example["phy_break_even_MC_p95"]):.3f}). The missing PHY input prevents deciding that inequality; '
        'this is NOT evidence that bandwidth halving necessarily reduces chip area.', '',
        '## 6. Paper Data And Figures', '',
        *table([dict(file=name,purpose=purpose) for name,purpose in (
            ('selection_comparison.csv','22 Box rows; explicit global-cost blocker'),
            ('selection_comparison_within_memory.csv','Same-tier conditional area MC and empirical stresses'),
            ('symbolic_cost_candidates.csv','Positive-resource-undominated alternatives with symbolic PHY term'),
            ('parametric_bandwidth_pairs.csv','Cross-bandwidth symbolic PHY break-even sensitivity'),
            ('energy_selection_HBM2_only.csv','Separate energy objective on known HBM2 subset'),
            ('candidate_points.csv','All retained primary curves incl unbatched/controls; provenance preserved'),
            ('k_ablation_summary.csv','Four representative HW, LPDDR102.4GB/s4/8 cores mandatory; all five same-split controls'),
            ('seq_mapper_refresh_summary.csv','All100 mapper/refresh/front-end identities with median/min/max gates'),
            ('native_instance_controls.csv','MOP aggregate/independent and outstanding512/8192 controls, unsupported cases retained'),
            ('frontier_by_memory.csv','One retained L/S frontier per eligible memory tier'),
            ('when_batching_selected.csv','Fixed-HW lowest-L mapping at S targets; descriptive reasons, not causal proof'),
            ('selected_rechecks/','960-request original vs compiled request evidence'),
            ('selected_stress/','All raw fixed-period empirical stress timestamps'),
            ('figures/','Three PNG scientific plots; pixel/nonblank/text-bounds QA, no human visual inspection'))],['file','purpose']), '',
        'All listed files are under `results/v6/paper/`. k controls retain DiT GB/request, busy fractions, Tmin/L/S, '
        'compute/exposed-memory/linear/attention/wait round components; the same allocation is used within each hardware. '
        'Traffic conservation and both time decompositions were independently audited in every repaired evaluation.', '',
        '## 7. Task Measurement Request', '',
        f'`task/measurement_request.md`: {task["points"]} unique proposed L/S points, including six additional distinct L<100ms points. '
        'The list covers conditional per-memory area selections, NOT finalized global-cost choices. '
        'Closed-loop task episodes added: **0**. Checkpoint, environment, speed bands, budget, success/invalid criteria, '
        'injection implementation and chunk adoption are external inputs left null. No synthetic outcomes/checkpoints.', '',
        'Each point/speed must report trials/successes/invalid separately. Mandatory invalid-as-failure K/N and '
        'invalid-excluded K/(N-I) summaries; all-invalid excluded rate is null. `v6_task.py validate` validates genuine supplied '
        'counts and metadata, never launches an environment or produces successes. The blank results template intentionally fails validation.', '',
        '## 8. Failures, Limits And Reproduction', '',
        f'Input specification provenance: `{input_spec["archived"]}`; origin={input_spec["origin"]}. '
        'The original Downloads path was fully read at the start but had disappeared by publication. The explicitly marked '
        'tool-readback reconstruction preserves the executed requirements; byte identity to the unavailable original cannot '
        'be verified. No Downloads files were restored or modified. See `input_spec_provenance.json`.', '',
        'Preserved failures: local seq collector initially called digest on str instead of Path; valid completed raw native '
        'results and failure.json retained, corrected successful local run separate. Initial synthesis library filename/metadata '
        'handling failures preserved in prior logs. Initial seq preparation assumed a per-item seq field instead of the actual '
        'global seq_traces; fixed before the frozen input manifest. Known implementation errors: `execution/implementation_failures.json`. '
        'Wrong F1 venue URL404 corrected via author page. '
        'Initial band control-cache alias was detected by independent raw L/S reconstruction; all affected controls were rerun '
        'in a separate frozen source/output identity, not silently repaired in place. '
        'Plot QA initially included a nonrendered out-of-view tick; corrected to inspect actual in-view tick labels. '
        'Executed collector/plot/finisher sources before these presentation changes are archived in finish/attempt_1; '
        'resume dependencies pin the previously completed numeric audits and stage tests. '
        'Rambus guessed PDFs404 and landing page redirects to login; IEEE/ACM retrieval did not yield verified numeric inputs. '
        'Correct NVIDIA source found through public publications search, no access controls bypassed. '
        'See `cost/sources/discovery/status.json` and `execution/` for limitations, Slurm IDs2050674/2051916 and accounting.', '',
        'Uncovered/degraded: four cost coefficients; no SRAM access-byte counter; no routed/clock-tree/internal switching power; '
        'no physical timing closure; no fresh heldout execution; W5 causal decomposition unresolved; NoRefresh GDDR acceptance; '
        'unsupported nonpower aggregate mapper; heuristic optimization pruning; empirical stresses are not confidence limits; '
        'HBM2 energy-subset choices not all960 rechecked; conditional task list not finalized global-cost list. '
        'These limit paper claims and are not silently marked complete.', '',
        *table(tests,['file','tests','failures']), '',
        'Reproduction (all run from repository root; existing stages resume by checkpoint):', '',
        '```sh',
        '# Input preparation is one-shot; skip when frozen manifests already exist.',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_prepare.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_remote.py seq',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py select',
        '# prepare is one-shot; reuse frozen repair_input/manifest.json on resume',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_remote.py repair',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py collect',
        'OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=vlasim .venv/bin/python vlasim/v6_repair.py dse --workers 4',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_band.py run --workers 4',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_control_band.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_audit.py band',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_arbiter.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_finish.py',
        'PYTHONPATH=vlasim .venv/bin/python vlasim/v6_report.py verify',
        '```', '',
        'Synthesis reproduction: official HardFloat source and exact Liberty files are archived under cost/synth; '
        '`PYTHONPATH=vlasim .venv/bin/python vlasim/v6_synth.py`, then `v6_rtl_check.py`. '
        'Optional tool versions and source hashes are archived; no dependency metadata churn in the existing repo.', '',
        f'Preservation: V5.1 {preserved["v5_1"]["artifacts"]} artifacts and{preserved["v5_1"]["sources"]} source/report hashes unchanged; '
        f'earlier deliveries{sum(r["artifacts"] for r in preserved["earlier"])} artifacts unchanged. '
        'Final V6 artifacts, source files, input specification and this report are SHA256-pinned in `results/v6/delivery_manifest.json`. '
        'Verification record is deliberately outside its own manifest; it pins the manifest hash and does not create a recursive hash dependency.', '',
        'External unblock request: `cost/external_input_request.json`. Supply traceable per-type PHY area and DRAM+I/O energy '
        'with width/rate/node/voltage/scope and uncertainty. Then fill the coefficients, rerun global cost optimization and '
        'selected-point stresses, regenerate the task list. Existing native/DSE/error-band evidence does not need to be fabricated or discarded.']
    Path('docs/CASE_V6_REPORT.md').write_text('\n'.join(lines)+'\n')
    write_json(ROOT/'execution/environment.json',dict(platform=platform.platform(),python=sys.version,numpy=np.__version__,
        compute_snapshot_sha256=digest('.native/compute/source_manifest.json'),
        compute_expected_sha256=load('results/case_v3_complete/experiment_manifest.json')['compute_snapshot_sha256']))
    excluded={'delivery_manifest.json','delivery_verification.json'}
    artifacts={str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in excluded}
    sources=[*Path('vlasim').glob('v6*.*'),Path('vlasim/ramulator_bridge/v6_native.py'),Path('scripts/einst_v6.sh'),
        *Path('tests').glob('test_v6*.py'),Path('docs/CASE_V6_REPORT.md')]
    write_json(ROOT/'delivery_manifest.json',dict(status=status['status'],artifacts_sha256=artifacts,
        sources_sha256={str(p):digest(p) for p in sources if p.is_file()},task_episodes_run=0,
        scope='Feasible work delivered with explicit external cost blockers, not all V6 goals satisfied.'))
    print('Published V6 report',len(artifacts),'artifacts',flush=True)


def verify():
    manifest=load(ROOT/'delivery_manifest.json')
    for root,entries in ((ROOT,manifest['artifacts_sha256']),(Path('.'),manifest['sources_sha256'])):
        for name,sha in entries.items():
            if not (root/name).is_file() or digest(root/name)!=sha:raise RuntimeError('Delivery hash mismatch '+name)
    for path in ('validation/native_audit.json','validation/dse_archive_audit.json','band/audit.json'):
        if not load(ROOT/path)['passed']:raise RuntimeError('Failed final gate '+path)
    if load(ROOT/'execution/environment.json')['compute_snapshot_sha256']!=load(ROOT/'execution/environment.json')['compute_expected_sha256']:
        raise RuntimeError('HARD_STOP_compute_snapshot_changed')
    if load(ROOT/'task/status.json')['task_episodes_run']!=0:raise RuntimeError('Unexpected task episodes')
    if len(read_csv(ROOT/'paper/selection_comparison.csv'))!=22:raise RuntimeError('Missing Box rows')
    if any(r['serial_point_id'] or r['task_point_id'] for r in read_csv(ROOT/'paper/selection_comparison.csv')):
        raise RuntimeError('Unverified external inputs must not yield global selections')
    current={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name not in ('delivery_manifest.json','delivery_verification.json')}
    if current!=set(manifest['artifacts_sha256']):raise RuntimeError('Unmanifested delivery artifact')
    write_json(ROOT/'delivery_verification.json',dict(passed=True,manifest_sha256=digest(ROOT/'delivery_manifest.json'),
        artifacts=len(manifest['artifacts_sha256']),sources=len(manifest['sources_sha256']),
        status=manifest['status'],global_cost_goals_satisfied=False))
    print('Verified V6 delivery:',len(manifest['artifacts_sha256']),'artifacts;',len(manifest['sources_sha256']),'sources/report',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('publish','verify'));a=p.parse_args()
    publish() if a.action=='publish' else verify()
