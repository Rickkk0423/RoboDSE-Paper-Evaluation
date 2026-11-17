"""Collect DSE checkpoints, reference-confirmed frontiers and task-preparation demo."""
from collections import Counter,defaultdict
import csv
import gzip
import json
from pathlib import Path
import shutil
import sys

import numpy as np

from case_v3_main import write_csv
from v51_workflow import ROOT,load
from v5_protocol import digest,write_json
from v4_task_data import sampling_plan,trial_schema,example_template

sys.path.insert(0,str(Path(__file__).parent/'analysis'))
from task_report import TaskGrid


def read_csv(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def frontier(rows):
    output=[];best=float('inf')
    for row in sorted(rows,key=lambda r:(float(r['S_s']),float(r['L_s']))):
        latency=float(row['L_s'])
        if latency<best-1e-12:
            output.append(row);best=latency
    return output


def concatenate(paths,destination,transform=None,extra_fields=()):
    fields=[]
    for path in paths:
        with path.open(newline='') as stream:
            for field in csv.DictReader(stream).fieldnames or []:
                if field not in fields:
                    fields.append(field)
    fields.extend(k for k in extra_fields if k not in fields)
    with destination.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for path in paths:
            with path.open(newline='') as source:
                rows=csv.DictReader(source)
                writer.writerows(transform(r) for r in rows) if transform else writer.writerows(rows)


def collect():
    shards=sorted((ROOT/'dse/shards').glob('*'))
    if len(shards)!=80 or any(not (s/'status.json').exists() for s in shards):
        raise RuntimeError('DSE requires all 80 completed memory/core shards')
    calibrations=load(ROOT/'calibration.json')
    calibration_hashes={memory:digest(ROOT/'calib'/f'dram_v51_{memory}.json') for memory in calibrations}
    coverage={}
    frozen=load(ROOT/'heldout_manifest.json')
    for index,item in enumerate(frozen['items']):
        state=load(ROOT/f'heldout_native/shard_{index}/status.json')
        windows=[r for r in state['rows'] if r['task']['window']=='W5']
        if windows:
            coverage[item['config']['id'],bool(item['bg'])]='unverifiable_capacity' if any('result' not in r for r in windows) else 'native_completed_model_gate_separate'
    def enrich(row):
        cal=calibrations[row['memory']];geometry=cal['geometry'];config=cal['config']
        bg=row.get('bg') in (True,'True')
        params=cal['baseline']['bg' if bg else 'plain']['params'] if row.get('model')=='v3_form' else cal['params']['vla_bg' if bg else 'vla_plain']
        layout_coverage=coverage.get((row['memory'],bg),'not_selected_for_heldout')
        return dict(row,standard=config['standard'],channels=config['channels'],organization=config['organization'],
            timing=config['timing'],controller=config['controller'],refresh=config['refresh'],mapper=cal['mapper'],
            array_rows=128,array_cols=128,freq_hz=1e9,dram_bw=geometry['peak_GBps']*1e9,
            slice_mode=row.get('track')=='analytical_sliced',dram_priority=False,
            compute_status='estimated_shapes_explicit_SigLIP_analytical_fallback' if row.get('track')=='neusim_unsliced' else 'analytical_slicing_sensitivity_unvalidated',
            actual_peak_GBps=geometry['peak_GBps'],capacity_bytes=geometry['capacity_bytes'],
            aggregate_bus_bits=geometry['aggregate_bus_bits'],calibration_identity_sha256=calibration_hashes[row['memory']],
            eta_seq=params['eta_seq'],eta_mix=params['eta_mix'],prio_leak=params['prio_leak'],
            W5_sampling_control_status=cal['sampling']['status'],W5_layout_heldout_coverage=layout_coverage,
            W5_status='W5_BG_unverified_capacity' if layout_coverage=='unverifiable_capacity' else
                'W5_BG_unverified_no_layout_holdout' if bg and layout_coverage=='not_selected_for_heldout' else
                row.get('W5_status',cal['sampling']['status']))
    grid=[];ablations=[];audits={};summaries=[];groups=defaultdict(list);curve_count=0
    for shard in shards:
        status=load(shard/'status.json');summaries.append(status)
        for name,sha in status['hashes'].items():
            if digest(shard/name)!=sha:
                raise RuntimeError('HARD_STOP_DSE_shard_hash_mismatch')
        grid.extend(enrich(r) for r in read_csv(shard/'hw_grid.csv'))
        with (shard/'curves.csv').open(newline='') as stream:
            for row in csv.DictReader(stream):
                curve_count+=1
                if row['curve_gate']!='True' or row['dit_batching']!='True':
                    continue
                row=enrich(row)
                key=tuple(row[k] for k in ('hardware_id','model','track','bw_policy','scenario'))
                l,s=float(row['L_s']),float(row['S_s'])
                existing=groups[key]
                if any(float(r['L_s'])<=l and float(r['S_s'])<=s for r in existing):
                    continue
                groups[key]=[r for r in existing if not(l<=float(r['L_s']) and s<=float(r['S_s']))]+[row]
        ablations.extend(enrich(r) for r in read_csv(shard/'k_ablation.csv'))
        for audit in load(shard/'rechecks.json'):
            audits[audit['config_id'],str(audit['factor'])]=audit
    supplement=ROOT/'dse/ablation_supplement/controls.csv'
    if not supplement.exists() or load(ROOT/'dse/ablation_supplement/status.json')['input_completed_shards']!=80:
        raise RuntimeError('Required all-pruned pipeline ablation supplement missing')
    removed=[r for r in ablations if r['status'].startswith('N/A') and int(r['n_cores'])>1]
    ablations=[r for r in ablations if not(r['status'].startswith('N/A') and int(r['n_cores'])>1)]
    for row in ablations:
        if row['status'].startswith('N/A'):
            row['status']='N/A_single_core_no_pipeline'
    ablations.extend(enrich(r) for r in read_csv(supplement))
    attainable=[];best_rows=[];recheck_failed=[]
    for key,rows in groups.items():
        selected=frontier(rows)
        verified=[]
        for row in selected:
            audit=audits.get((row['config_id'],str(float(row['factor']))))
            if audit is None:
                raise RuntimeError('Frontier missing canonical 960 request reference audit '+row['config_id'])
            if not audit['gate']['pass_gate']:
                recheck_failed.append(dict(config_id=row['config_id'],factor=row['factor'],audit=audit))
                continue
            value={**row,'L_s':audit['gate']['L_mean_s'],'S_s':audit['gate']['S_mean_s'],
                'canonical960_pass':True,'reference960_max_error_s':audit['reference_max_done_error_s']}
            attainable.append(value)
            verified.append(value)
        for target in (50,100,150,200):
            feasible=[r for r in verified if float(r['S_s'])*1000<=target+1e-9]
            if feasible:
                best_rows.append(dict(min(feasible,key=lambda r:float(r['L_s'])),S_target_ms=target,status='attainable',
                    optimality_scope='lowest_L_among_reference_verified_retained_five_point_curves_not_continuous_global_optimum'))
            else:
                best_rows.append(dict(**dict(zip(('hardware_id','model','track','bw_policy','scenario'),key)),
                    S_target_ms=target,status='no_verified_point_at_target'))
    write_csv(ROOT/'hw_grid.csv',grid);write_csv(ROOT/'attainable.csv',attainable)
    write_csv(ROOT/'best_mapping.csv',best_rows)
    sensitivity=defaultdict(list)
    for row in attainable:
        if row['bw_policy']=='fair' and row['scenario']=='main' and row['sram_mb']=='64' and row['local_kb']=='512':
            sensitivity[row['memory'],row['n_cores'],row['model'],row['track']].append(row)
    sensitivity_rows=[]
    for key,points in sensitivity.items():
        fastest=min(points,key=lambda r:float(r['S_s']));lowest=min(points,key=lambda r:float(r['L_s']))
        sensitivity_rows.append(dict(memory=key[0],n_cores=key[1],model=key[2],track=key[3],
            configured_peak_GBps=fastest['actual_peak_GBps'],min_S_s=fastest['S_s'],L_at_min_S_s=fastest['L_s'],
            min_S_mode=fastest['mode'],min_S_k=fastest['dit_stages'],min_S_vlm_cores=fastest['vlm_cores'],
            min_L_s=lowest['L_s'],S_at_min_L_s=lowest['S_s'],min_L_mode=lowest['mode'],min_L_k=lowest['dit_stages'],
            shared_MB=64,private_KB=512,scope='Separate extrema over retained reference-confirmed discrete curves, not a jointly attainable extrema pair.'))
    write_csv(ROOT/'sensitivity_core_bandwidth.csv',sensitivity_rows)
    round_cache={}
    for row in ablations:
        if not row.get('semantic_id') or not row.get('Tmin_s'):
            continue
        path=ROOT/row['raw'] if row.get('raw') else ROOT/f'dse/shards/{row["memory"]}_c{row["n_cores"]}/evaluations/{row["semantic_id"]}/requests.npz'
        key=str(path)
        if key not in round_cache:
            with np.load(path) as raw:
                requests=raw['requests'][-5];rounds=raw['curve_rounds_0']
                k=int(row['dit_stages']);lo=requests[96,3];hi=requests[480-k-3,3]
                selected=rounds[(rounds[:,0]>=lo)&(rounds[:,1]<=hi)&(rounds[:,11]==0)]
                round_cache[key]=dict(round_dram_GB=float(selected[:,7].mean()/1e9) if len(selected) else None,
                    round_weight_GB=float(selected[:,8].mean()/1e9) if len(selected) else None,
                    round_active_requests=float(np.mean([int(mask).bit_count() for mask in selected[:,10]])) if len(selected) else None)
        row.update(round_cache[key])
    write_csv(ROOT/'k_ablation.csv',ablations)
    compute_groups=defaultdict(list)
    def scalar(value):
        if value in (None,''):
            return None
        if value in ('True','False'):
            return value=='True'
        try:
            return float(value)
        except (ValueError,TypeError):
            return value
    for row in ablations:
        compute_groups[row['hardware_id'],row['model'],row['bg']].append({key:scalar(row.get(key)) for key in
            ('status','selected_split','dit_stages','dit_batching','Tmin_s','L_s','S_s','dit_GB_per_req',
             'steady_dit_GB_per_req','steady_KV_GB_per_req','vlm_busy','dit_busy','steady_vlm_busy','steady_dit_busy',
             'round_duration_s','round_compute_s','round_exposed_memory_s','round_linear_s','round_attention_s','round_wait_before_s',
             'round_dram_GB','round_weight_GB','round_active_requests')})
    write_json(ROOT/'compute_report.json',dict(scope='Same-allocation k ablation; '
        'raw request and per-round data in each semantic evaluation requests.npz; no fabricated pruned timings.',
        groups=[dict(hardware_id=k[0],model=k[1],bg=k[2]=='True',measurements=v) for k,v in compute_groups.items()]))
    effects=[]
    for key,members in compute_groups.items():
        batched=[r for r in members if r['dit_batching'] is True and r.get('Tmin_s') is not None]
        base=next((r for r in batched if r['dit_stages']==1.),None)
        if base is None:
            continue
        best=min(batched,key=lambda r:r['Tmin_s'])
        for row in batched:
            effects.append(dict(hardware_id=key[0],model=key[1],bg=key[2],k=row['dit_stages'],
                selected_split=row['selected_split'],best_throughput_k=best['dit_stages'],
                Tmin_ratio_to_k1=row['Tmin_s']/base['Tmin_s'],L_ratio_to_k1=row['L_s']/base['L_s'],
                DiT_traffic_ratio_to_k1=row['steady_dit_GB_per_req']/base['steady_dit_GB_per_req'],
                steady_vlm_busy=row['steady_vlm_busy'],steady_dit_busy=row['steady_dit_busy'],
                exposed_memory_fraction=row['round_exposed_memory_s']/row['round_duration_s'],
                diagnostic='round_cadence_wait_exceeds_active_round' if row['round_wait_before_s']>row['round_duration_s'] else
                    'VLM_high_busy_consistent_with_feed_limit' if row['steady_vlm_busy']>.95 else
                    'DiT_exposed_memory_dominant' if row['round_exposed_memory_s']>row['round_compute_s'] else 'DiT_compute_dominant',
                scope='Descriptive measured-model components, not proof of a unique bottleneck cause.'))
    write_csv(ROOT/'k_effects.csv',effects)
    extra=set(enrich(dict(memory=next(iter(calibrations)))))-{'memory'}
    concatenate([s/'curves.csv' for s in shards],ROOT/'all_curves.csv',enrich,sorted(extra))
    comparisons=[];contexts=defaultdict(list)
    for row in grid:
        if row['bw_policy']=='fair' and row['track']=='neusim_unsliced' and row.get('Tmin_s'):
            contexts[row['hardware_id'],row['model'],row['bg']].append(row)
    for key,members in contexts.items():
        serial=next((r for r in members if r['mode']=='serial'),None)
        pipelines=[r for r in members if r['mode']=='pipelined' and r['dit_batching']=='True']
        best=min(pipelines,key=lambda r:float(r['Tmin_s'])) if pipelines else None
        comparisons.append(dict(hardware_id=key[0],model=key[1],bg=key[2],
            serial_Tmin_s=float(serial['Tmin_s']) if serial else None,
            serial_L_at_Tmin_s=float(serial['L_factor_1.0_s']) if serial else None,
            pipeline_Tmin_s=float(best['Tmin_s']) if best else None,
            pipeline_L_at_Tmin_s=float(best['L_factor_1.0_s']) if best else None,
            pipeline_vlm_cores=best['vlm_cores'] if best else None,pipeline_k=best['dit_stages'] if best else None,
            pipeline_scope='best_retained_batched_pipeline' if best else 'N/A_single_core' if int(members[0]['n_cores'])==1
                else 'all_pipeline_mappings_optimization_pruned_not_proven_infeasible',
            scope='480_request_min_Tmin_controls; not necessarily an equal_S_latency_comparison'))
    write_csv(ROOT/'serial_pipeline_comparison.csv',comparisons)
    from vlasim.workload import Pi05Workload
    wl=Pi05Workload()
    write_json(ROOT/'sram_placement_summary.json',dict(
        scope='Existing static admission model, estimated checkpoint shapes; not measured SRAM lifetime.',
        vlm_activation_MB=wl.vlm_act_bytes/1e6,prefix_KV_per_request_MB=wl.kv_total_bytes/1e6,
        KV_and_activation_required_MB={str(k):(wl.vlm_act_bytes+wl.kv_total_bytes*(k+2))/1e6 for k in (1,2,3)},
        serial_KV_and_activation_required_MB=(wl.vlm_act_bytes+wl.kv_total_bytes)/1e6,
        grid_placement_context_counts=dict(Counter(
            f'{r["mode"]}:shared{r["sram_mb"]}:act{r["act_on_chip"]}:KV{r["kv_on_chip"]}' for r in grid))))
    write_json(ROOT/'frontier_recheck_failures.json',recheck_failed)
    evaluation_paths=list((ROOT/'dse/shards').glob('*/evaluations/*/status.json'))
    supplement_paths=list((ROOT/'dse/ablation_supplement/evaluations').glob('*/status.json'))
    search_trials=failed_trials=nonmonotonic=failed_curve_points=0
    for path in evaluation_paths+supplement_paths:
        evidence=load(path);trials=evidence['search']['trials'].values()
        search_trials+=len(evidence['search']['trials']);failed_trials+=sum(not t['pass_gate'] for t in trials)
        nonmonotonic+=bool(evidence['nonmonotonic'])
        failed_curve_points+=sum(not p['gate']['pass_gate'] for p in evidence['curve'])
    stats=dict(hardware_points=len({r['hardware_id'] for r in grid}),mapping_context_rows=len(grid),
        statuses=dict(Counter(r['status'] for r in grid)),curve_rows=curve_count,attainable_rows=len(attainable),
        reference_rechecks=sum(s['reference_rechecks'] for s in summaries),
        canonical960_failed_frontiers=len(recheck_failed),unique_semantic_evaluations=len(evaluation_paths),
        supplemental_semantic_evaluations=len(supplement_paths),search_trials=search_trials,failed_search_trials=failed_trials,
        observed_nonmonotonic_evaluations=nonmonotonic,failed_curve_points=failed_curve_points,
        unique_reference960_runs=len(list((ROOT/'dse/shards').glob('*/rechecks/*.json.gz'))),
        ablation_supplement_replaced_unexecuted_contexts=len(removed),
        ablation_supplement_rows=load(ROOT/'dse/ablation_supplement/status.json')['rows'],
        source_sha256=digest(__file__),costs={standard:dict(area=None,energy=None,status='placeholder_not_calibrated')
            for standard in ('LPDDR5','GDDR6','HBM2')},
        ablation_scope='Each hardware/model/layout selects its best batched Tmin pipeline allocation, then '
            'runs all k=1/2/3 batched and k=2/3 unbatched at that SAME split as separate required controls. '
            'If all pipeline allocations were optimization-pruned, use smallest-LB split as an explicit fallback. '
            'Optimization prunes stay unchanged; ablation controls are not optimization candidates.')
    write_json(ROOT/'dse_summary.json',stats)
    write_json(ROOT/'cost_placeholders.json',stats['costs'])
    gates=load(ROOT/'gates.json');gates['stage4']=dict(status='completed_with_reference_rechecks',**stats)
    write_json(ROOT/'gates.json',gates)
    for name in ('hw_grid.csv','all_curves.csv'):
        path=ROOT/name
        with path.open('rb') as source,(ROOT/(name+'.gz')).open('wb') as target:
            with gzip.GzipFile(filename='',mode='wb',fileobj=target,mtime=0) as compressed:
                shutil.copyfileobj(source,compressed)
    print(json.dumps(stats,indent=2))


def task_prep():
    out=ROOT/'task_preparation';out.mkdir(exist_ok=True)
    path=Path('vlasim/data/libero_dynamic_L_S.csv');grid=TaskGrid(path)
    rows=read_csv(ROOT/'attainable.csv');demo=[]
    for row in rows:
        l,s=float(row['L_s'])*1000,float(row['S_s'])*1000
        demo.append(dict(hardware_id=row['hardware_id'],config_id=row['config_id'],model=row['model'],
            track=row['track'],scenario=row['scenario'],L_ms=l,S_ms=s,
            **grid.lookup(l,s),scope='workflow_demo_only_not_task_or_chip_conclusion'))
    write_csv(out/'joint_selection_demo.csv',demo)
    primary=[r for r in demo if r['model']=='v51' and r['track']=='neusim_unsliced' and r['scenario']=='main']
    points=np.array([[r['L_ms'],r['S_ms']] for r in primary])
    recommendations=[]
    for point in sampling_plan():
        p=np.array([point['L_ms'],point['S_ms']]);distance=np.linalg.norm(points-p,axis=1)
        nearest=int(np.argmin(distance))
        recommendations.append(dict(**point,nearest_frontier_distance_ms=float(distance[nearest]),
            nearest_frontier_L_ms=primary[nearest]['L_ms'],nearest_frontier_S_ms=primary[nearest]['S_ms'],
            historical_coverage=grid.lookup(*p)['status'],
            priority='frontier_near_uncovered' if grid.lookup(*p)['status']=='outside_measured_hull' and distance[nearest]<=50
                else 'frontier_near' if distance[nearest]<=50 else 'far_from_current_frontier'))
    recommendations.sort(key=lambda r:(r['priority']!='frontier_near_uncovered',r['nearest_frontier_distance_ms']))
    write_csv(out/'suggested_measurements.csv',recommendations)
    write_json(out/'trial.schema.json',trial_schema());write_json(out/'example.template.json',example_template())
    write_json(out/'status.json',dict(status='preparation_only',measured_episodes=0,historical_aggregate_points=len(grid.points),
        proposed_points=len(recommendations),demo_rows=len(demo),historical_csv_sha256=digest(path),
        no_extrapolation=True,scope='Workflow demo, no new task measurements, no checkpoint/environment transfer claim, '
            'no per-speed denominator or chip ranking. Outside historical convex hull explicitly abstains.',
        missing_inputs=['closed_loop_environments_and_versions','checkpoint_hash','per_speed_trial_budget',
            'latency_injection','action_chunk_adoption','invalid_episode_definition']))


if __name__=='__main__':
    collect();task_prep()
