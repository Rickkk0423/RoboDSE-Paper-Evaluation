"""Paper-ready evidence with explicit cost-input blockers and conditional comparisons."""
import argparse
from collections import Counter,defaultdict
import csv
from pathlib import Path

import numpy as np

from v6_common import ROOT,OLD,load,write_json,write_csv,digest
from v51_package import read_csv,frontier
from v6_cost import estimate,feature

BOXES=[(l,s) for l in (100,150,200,250,300) for s in (50,75,100,150,200) if s<=l]


def primary(row):
    return row.get('model')=='v51' and row.get('track')=='neusim_unsliced' and row.get('bw_policy')=='fair' and row.get('bg') in (False,'False')


def enrich(row,root,cal):
    v=cal[row['memory']];g=v['geometry']
    return dict(row,actual_peak_GBps=g['peak_GBps'],dram_bw=g['peak_GBps']*1e9,
        calibration_identity_sha256=digest(root/'calibration.json'),
        evidence_root=str(root),eta_seq=v['params']['vla_plain']['eta_seq'],
        model_status='dual_model_DRAM_unvalidated_V6_identity_no_new_heldout' if root==ROOT else row.get('model_status'),
        native_frontend_outstanding=v.get('outstanding',512),native_mode=v.get('native_mode',g.get('mode','frozen_V5.1')))


def collect():
    import v51_ablation
    v51_ablation.ROOT=ROOT
    shards=sorted((ROOT/'dse/shards').glob('*/status.json'))
    if len(shards)!=24:
        raise RuntimeError('Require all 24 repaired DSE shards')
    for path in shards:
        status=load(path)
        for name,sha in status['hashes'].items():
            if digest(path.parent/name)!=sha:
                raise RuntimeError('HARD_STOP_DSE_shard_hash')
    v51_ablation.supplement()
    supplemental=ROOT/'dse/ablation_supplement/status.json'
    write_json(supplemental,dict(load(supplemental),expected_input_shards=24,
        adapter_source_sha256=digest(__file__),scope='Unchanged V5.1 supplementary evaluator on only24 repaired shards.'))
    cal=load(ROOT/'calibration.json');selected=load(ROOT/'repair_selection.json')['tiers']
    changed=set(selected);candidates=[];ablations=[];counts=Counter();rechecks=[]
    groups=defaultdict(list)
    for root in (OLD,ROOT):
        if root==OLD:
            sources=[root/'all_curves.csv'];abpaths=[root/'k_ablation.csv']
        else:
            sources=[p.parent/'curves.csv' for p in shards]
            abpaths=[p.parent/'k_ablation.csv' for p in shards]+[root/'dse/ablation_supplement/controls.csv']
        for path in sources:
            with path.open(newline='') as stream:
                for row in csv.DictReader(stream):
                    if root==ROOT:counts['repaired_curve_rows']+=1
                    if root==OLD and row['memory'] in changed:continue
                    if row['memory'] in selected and selected[row['memory']]['status']=='excluded_low_seq':continue
                    if not primary(row) or row['curve_gate']!='True':continue
                    row=enrich(row,root,cal)
                    row['candidate_source']='retained_search_curve'
                    row['timing_scope']='480_request_retained_curve; not every candidate has960 recheck'
                    candidates.append(row)
        for path in abpaths:
            for row in read_csv(path):
                if root==OLD and row['memory'] in changed:continue
                if row['memory'] in selected and selected[row['memory']]['status']=='excluded_low_seq':continue
                if primary(row) and row.get('Tmin_s') and row.get('curve_gate')=='True':
                    row=enrich(row,root,cal);ablations.append(row)
                    if row.get('dit_batching')=='False':
                        row=dict(row,T_s=row['Tmin_s'],candidate_source='required_unbatched_same_split_control',
                            timing_scope='480_request_control; not global optimization candidate')
                        row['config_id']=row.get('config_id') or row['semantic_id']+'_'+row['hardware_id']
                        candidates.append(row)
    # Confirm repaired search frontiers against the existing original-scheduler 960-request evidence.
    grid_statuses=Counter();hardware=set();context_rows=0
    for path in shards:
        directory=path.parent;audits={(r['config_id'],float(r['factor'])):r for r in load(directory/'rechecks.json')}
        for row in read_csv(directory/'hw_grid.csv'):
            grid_statuses[row['status']]+=1;hardware.add(row['hardware_id']);context_rows+=1
        localgroups=defaultdict(list)
        for row in read_csv(directory/'curves.csv'):
            if row['curve_gate']=='True' and row['dit_batching']=='True':
                localgroups[tuple(row[k] for k in ('hardware_id','model','track','bw_policy','scenario'))].append(row)
        for values in localgroups.values():
            for row in frontier(values):
                audit=audits.get((row['config_id'],float(row['factor'])))
                if audit is None or audit['reference_max_done_error_s']>1e-6:
                    raise RuntimeError('HARD_STOP_repaired_frontier_reference')
                rechecks.append(dict(config_id=row['config_id'],hardware_id=row['hardware_id'],factor=row['factor'],
                    L_s=audit['gate']['L_mean_s'],S_s=audit['gate']['S_mean_s'],
                    pass_gate=audit['gate']['pass_gate'],reference_max_error_s=audit['reference_max_done_error_s']))
    unique={}
    for row in candidates:
        key=(row['memory'],row['hardware_id'],row['mode'],str(row['vlm_cores']),str(row['dit_stages']),
            str(row['dit_batching']),float(row['T_s']))
        unique.setdefault(key,row)
    candidates=list(unique.values())
    for index,row in enumerate(candidates):row['point_id']=f'v6p{index:06d}'
    paper=ROOT/'paper';paper.mkdir(exist_ok=True)
    write_csv(paper/'candidate_points.csv',candidates);write_csv(paper/'all_k_controls.csv',ablations)
    write_csv(ROOT/'repaired_frontier_rechecks.csv',rechecks)
    write_json(paper/'collection.json',dict(**counts,candidate_points=len(candidates),
        source_counts=dict(Counter(r['candidate_source'] for r in candidates)),
        repaired_hardware_points=len(hardware),repaired_context_rows=context_rows,
        repaired_context_statuses=dict(grid_statuses),completed_shards=24,reference_frontiers=len(rechecks),
        reference_failed=sum(not r['pass_gate'] for r in rechecks),
        eligibility='VLA model, NeuSim unsliced, fair, plain, median eta_seq>=0.8. GDDR accepted conditionally NoRefresh.',
        limitations='All retained discrete curves INCLUDING unbatched plus required unbatched controls. Original '
            'LB>1.2*incumbent optimization pruning retained; no global optimum claim. Controls may expand retained '
            'candidate set but do not erase old pruning evidence. Later selected points receive960-request audit.'))
    print('Collected',len(candidates),'paper candidate points',flush=True)


def best(rows,c):
    return min(rows,key=lambda r:(float(feature(r)@c),round(float(r['L_s']),9),
        round(float(r['S_s']),9),r['point_id'])) if rows else None


def latency_candidate(row,smax):
    # Slower serial observation periods are not the specification's S=L baseline.
    return row['mode']=='serial' and abs(float(row['T_s'])-float(row['Tmin_s']))<1e-10 and float(row['L_s'])*1000<=smax+1e-9


def selection():
    points=read_csv(ROOT/'paper/candidate_points.csv');c=load(ROOT/'cost/coefficients.json')['coefficients']
    check=ROOT/'paper/selected_recheck_status.json'
    if check.exists():
        audited={p.parent.name:load(p) for p in (ROOT/'paper/selected_rechecks').glob('*/status.json')}
        failed={key for key,value in audited.items() if not value['gate']['pass_gate']}
        points=[r for r in points if r['point_id'] not in failed]
        for row in points:
            audit=audited.get(row['point_id'])
            if audit:
                row.update(L_s=audit['gate']['L_mean_s'],S_s=audit['gate']['S_mean_s'],timing_scope='canonical960_original_scheduler_pass')
    center=np.array([c[k]['value'] for k in ('A_core','a_sram','A_misc')])
    with np.load(ROOT/'cost/draws.npz') as data:
        keys=list(data['keys']);matrix=data['samples'][:,[keys.index(k) for k in ('A_core','a_sram','A_misc')]]
    output=[];conditional=[];chosen={};memory=sorted({r['memory'] for r in points});symbolic=[]
    for lmax,smax in BOXES:
        feasible=[r for r in points if float(r['L_s'])*1000<=lmax+1e-9 and float(r['S_s'])*1000<=smax+1e-9]
        serial=[r for r in points if latency_candidate(r,smax)]
        output.append(dict(Lmax_ms=lmax,Smax_ms=smax,latency_only_reachable=bool(serial),task_aware_reachable=bool(feasible),
            serial_candidates=len(serial),task_candidates=len(feasible),
            same_design=None,task_only_reachable=bool(feasible) and not serial,
            serial_point_id=None,task_point_id=None,serial_hardware=None,task_hardware=None,
            serial_mapping=None,task_mapping=None,serial_L_ms=None,serial_S_ms=None,task_L_ms=None,task_S_ms=None,
            serial_area_lower_mm2=None,serial_area_upper_mm2=None,task_area_lower_mm2=None,task_area_upper_mm2=None,
            serial_energy_lower_mJ=None,serial_energy_upper_mJ=None,task_energy_lower_mJ=None,task_energy_upper_mJ=None,
            bandwidth_ratio=None,core_ratio=None,MC_task_cost_lower_fraction=None,error_band_robust_fraction=None,
            status='BLOCKED_global_cost_selection_missing_PHY_and_DRAM_energy',
            conditional_data='selection_comparison_within_memory.csv; PHY cancels only within same memory tier',
            objective='Area primary; energy objective separately blocked, never a weighted scalar.'))
        for mem in memory:
            a=best([r for r in serial if r['memory']==mem],center)
            b=best([r for r in feasible if r['memory']==mem],center)
            row=dict(Lmax_ms=lmax,Smax_ms=smax,memory=mem,scope='CONDITIONAL_within_same_memory_tier_only',
                serial_reachable=a is not None,task_reachable=b is not None,
                task_only_reachable=b is not None and a is None,
                global_optimum=False,PHY_cancellation=True,
                error_band_robust_fraction=None)
            for prefix,value in (('serial',a),('task',b)):
                if value:
                    chosen[value['point_id']]=value
                    row.update({prefix+'_'+key:value[key] for key in ('point_id','hardware_id','mode','vlm_cores',
                        'dit_stages','dit_batching','L_s','S_s','T_s','actual_peak_GBps','n_cores')})
                    row.update({prefix+'_'+k:v for k,v in estimate(value,c).items()})
            if a and b:
                difference=feature(b)-feature(a);delta=matrix@difference
                row.update(same_design=a['point_id']==b['point_id'],
                    same_hardware=a['hardware_id']==b['hardware_id'],
                    area_difference_value_mm2=float(difference@center),
                    MC_task_area_lower_fraction=float(np.mean(delta<-1e-12)),
                    MC_task_area_not_higher_fraction=float(np.mean(delta<=1e-12)),
                    bandwidth_ratio=float(b['actual_peak_GBps'])/float(a['actual_peak_GBps']),
                    core_ratio=float(b['n_cores'])/float(a['n_cores']),
                    ranking_scope='2000 common coefficient draws, fixed nominal within-tier pair. Unknown same-tier PHY cancels exactly; '
                        'not global ranking or a probability of true costs.')
            conditional.append(row)
        # Symbolic candidates are reduced only by positive-cost hardware resource dominance.
        for protocol,rows in (('latency_only',serial),('task_aware',feasible)):
            hw={}
            for r in rows:
                key=r['hardware_id']
                if key not in hw or (float(r['L_s']),float(r['S_s']))<(float(hw[key]['L_s']),float(hw[key]['S_s'])):hw[key]=r
            for mem in memory:
                values=[r for r in hw.values() if r['memory']==mem]
                for r in values:
                    x=feature(r)[:2]
                    if any(np.all(feature(q)[:2]<=x) and np.any(feature(q)[:2]<x) for q in values):continue
                    symbolic.append(dict(Lmax_ms=lmax,Smax_ms=smax,protocol=protocol,point_id=r['point_id'],
                        hardware_id=r['hardware_id'],memory=mem,n_cores=r['n_cores'],sram_total_MB=x[1],
                        phy_channels=int(mem.split('_c')[-1]),A_core_multiplier=x[0],a_sram_multiplier=x[1],
                        A_phy_coefficient='A_phy_'+mem.split('_')[0],A_misc_multiplier=1.,
                        scope='Within-tier resource-undominated symbolic alternatives; no cross-type invented cost.'))
    write_csv(ROOT/'paper/selection_comparison.csv',output)
    write_csv(ROOT/'paper/selection_comparison_within_memory.csv',conditional)
    write_csv(ROOT/'paper/symbolic_cost_candidates.csv',symbolic)
    write_csv(ROOT/'paper/selected_conditional_points.csv',list(chosen.values()))
    write_json(ROOT/'paper/selection_status.json',dict(boxes=len(output),conditional_comparisons=len(conditional),
        selected_unique_points=len(chosen),global_cost_selection='BLOCKED_missing_external_inputs',
        conditional_pairs=sum(r['serial_reachable'] and r['task_reachable'] for r in conditional),
        conditional_lower_cost_pairs=sum(r.get('area_difference_value_mm2',0)<-1e-12 for r in conditional),
        global_robustness_fraction=None,conditional_data_not_global=True))
    print('Conditional unique points',len(chosen),flush=True)


def parametric():
    points=read_csv(ROOT/'paper/candidate_points.csv');c=load(ROOT/'cost/coefficients.json')['coefficients']
    center=np.array([c[k]['value'] for k in ('A_core','a_sram','A_misc')])
    with np.load(ROOT/'cost/draws.npz') as data:
        keys=list(data['keys']);matrix=data['samples'][:,[keys.index(k) for k in ('A_core','a_sram','A_misc')]]
    rows=[]
    for lmax,smax in BOXES:
        for standard in ('LPDDR5','GDDR6','HBM2'):
            members=[r for r in points if r['memory'].split('_')[0]==standard]
            serial=[r for r in members if latency_candidate(r,smax)]
            task=[r for r in members if float(r['L_s'])*1000<=lmax+1e-9 and float(r['S_s'])*1000<=smax+1e-9]
            if not serial or not task:continue
            def key(r):return float(r['actual_peak_GBps']),float(feature(r)@center),float(r['L_s']),r['point_id']
            a=min(serial,key=key);b=min(task,key=key)
            difference=feature(b)-feature(a);delta_channels=int(b['memory'].split('_c')[-1])-int(a['memory'].split('_c')[-1])
            row=dict(Lmax_ms=lmax,Smax_ms=smax,standard=standard,
                serial_point_id=a['point_id'],task_point_id=b['point_id'],serial_hardware=a['hardware_id'],task_hardware=b['hardware_id'],
                serial_L_ms=float(a['L_s'])*1000,serial_S_ms=float(a['S_s'])*1000,
                task_L_ms=float(b['L_s'])*1000,task_S_ms=float(b['S_s'])*1000,
                task_k=b['dit_stages'],task_batching=b['dit_batching'],
                bandwidth_ratio=float(b['actual_peak_GBps'])/float(a['actual_peak_GBps']),
                core_ratio=float(b['n_cores'])/float(a['n_cores']),
                area_difference_known_mid_mm2=float(difference@center),area_difference_PHY_multiplier=delta_channels,
                area_difference_formula='known_difference + delta_channels * unknown_A_phy_'+standard,
                scope='Bandwidth-minimizing illustration within standard, then minimum known area; NOT minimum total cost. '
                    'Linear channel PHY assumption explicit; unknown input is not assigned a number.')
            if delta_channels:
                thresholds=-(matrix@difference)/delta_channels
                row.update(phy_break_even_mid_mm2_per_channel=-float(difference@center)/delta_channels,
                    phy_break_even_MC_p5=float(np.quantile(thresholds,.05)),phy_break_even_MC_p50=float(np.quantile(thresholds,.5)),
                    phy_break_even_MC_p95=float(np.quantile(thresholds,.95)),
                    task_cheaper_condition='A_phy > break_even' if delta_channels<0 else 'A_phy < break_even')
            else:
                row.update(task_cheaper_condition='independent_of_common_PHY',
                    MC_task_area_lower_fraction=float(np.mean(matrix@difference<-1e-12)))
            rows.append(row)
    write_csv(ROOT/'paper/parametric_bandwidth_pairs.csv',rows)


def figures():
    points=read_csv(ROOT/'paper/candidate_points.csv');ab=read_csv(ROOT/'paper/all_k_controls.csv')
    variants=defaultdict(list)
    for row in read_csv(ROOT/'seq_comparison.csv'):variants[row['variant']].append(row)
    seq=[]
    for variant,values in variants.items():
        etas=[float(r['eta_seq']) for r in values if r['eta_seq']]
        r=values[0]
        seq.append(dict(memory=r['memory'],variant=variant,mapper=r['mapper'],refresh=r['refresh'],
            mode=r['mode'],outstanding=r['outstanding'],completed_grains=len(etas),
            eta_median=float(np.median(etas)) if len(etas)==3 else None,
            eta_min=min(etas) if etas else None,eta_max=max(etas) if etas else None,
            median_gate=len(etas)==3 and float(np.median(etas))>=.8,
            strict_all_grains_gate=len(etas)==3 and min(etas)>=.8,
            status='completed' if len(etas)==3 else r['status'],reason=r.get('reason')))
    write_csv(ROOT/'paper/seq_mapper_refresh_summary.csv',seq)
    write_csv(ROOT/'paper/native_instance_controls.csv',[r for r in seq if r['mapper']=='MOP4CLXOR'])
    front=[]
    for memory in sorted({r['memory'] for r in points}):
        front.extend(dict(r,scope='Retained discrete primary-model attainable frontier, conditional NoRefresh where GDDR.')
            for r in frontier([p for p in points if p['memory']==memory]))
    write_csv(ROOT/'paper/frontier_by_memory.csv',front)
    representative=[('LPDDR5_c8',4),('LPDDR5_c8',8),('GDDR6_c24',4),('HBM2_c32',4)]
    controls=[r for r in ab if (r['memory'],int(r['n_cores'])) in representative and float(r['sram_mb'])==64 and int(r['local_kb'])==512]
    write_csv(ROOT/'paper/k_ablation_summary.csv',controls)
    rows=[]
    for memory in sorted({r['memory'] for r in points}):
        for cores in sorted({int(r['n_cores']) for r in points if r['memory']==memory}):
            subset=[r for r in points if r['memory']==memory and int(r['n_cores'])==cores and float(r['sram_mb'])==64 and int(r['local_kb'])==512]
            for target in (50,75,100,150,200):
                feasible=[r for r in subset if float(r['S_s'])*1000<=target+1e-9]
                if not feasible:continue
                chosen=min(feasible,key=lambda r:float(r['L_s']))
                is_k2=chosen['mode']=='pipelined' and chosen['dit_stages']=='2' and chosen['dit_batching']=='True'
                controls_here=[r for r in ab if r['memory']==memory and int(r['n_cores'])==cores and float(r['sram_mb'])==64
                    and int(r['local_kb'])==512 and r.get('dit_stages')=='2' and r.get('dit_batching')=='True']
                control=controls_here[0] if controls_here else {}
                serial=any(r['mode']=='serial' for r in feasible)
                k2=[r for r in feasible if r['mode']=='pipelined' and r['dit_stages']=='2' and r['dit_batching']=='True']
                def value(key):return float(control[key]) if control.get(key) not in (None,'') else None
                busy=value('steady_vlm_busy');compute=value('round_compute_s');memory_time=value('round_exposed_memory_s')
                diagnostic='no_executed_k2_control' if not control else 'VLM_high_busy_consistent_with_feed_limit' if busy is not None and busy>.95 else \
                    'DiT_compute_dominant_in_same_split_control' if compute is not None and memory_time is not None and compute>=memory_time else \
                    'DiT_exposed_memory_dominant_in_same_split_control'
                rows.append(dict(memory=memory,n_cores=cores,S_target_ms=target,bandwidth_GBps=chosen['actual_peak_GBps'],
                    selected_mode=chosen['mode'],selected_k=chosen['dit_stages'],selected_batching=chosen['dit_batching'],
                    selected_L_s=chosen['L_s'],selected_S_s=chosen['S_s'],k2_batching_selected=is_k2,
                    reason='k2_lowest_retained_L_at_target' if is_k2 else 'serial_selected_and_feasible' if chosen['mode']=='serial' else
                        'no_retained_k2_point_meets_S_target' if not k2 else 'another_mapping_has_lower_retained_L',serial_feasible=serial,
                    k2_feasible_at_target=bool(k2),k2_best_L_s=min((float(r['L_s']) for r in k2),default=None),
                    observed_same_split_bottleneck=diagnostic,
                    observed_steady_vlm_busy=control.get('steady_vlm_busy'),observed_steady_dit_busy=control.get('steady_dit_busy'),
                    round_compute_s=control.get('round_compute_s'),round_exposed_memory_s=control.get('round_exposed_memory_s'),
                    scope='Latency-optimal mapping at fixed hardware/S, not global cost selection; descriptive metrics do not prove causation.'))
    write_csv(ROOT/'paper/when_batching_selected.csv',rows)


def energy():
    points=[r for r in read_csv(ROOT/'paper/candidate_points.csv') if r['memory'].startswith('HBM2_')]
    c=load(ROOT/'cost/coefficients.json')['coefficients'];costs={r['point_id']:estimate(r,c) for r in points}
    with np.load(ROOT/'cost/draws.npz') as data:
        keys=list(data['keys']);samples=data['samples']
    rows=[]
    for lmax,smax in BOXES:
        serial=[r for r in points if latency_candidate(r,smax)]
        task=[r for r in points if float(r['L_s'])*1000<=lmax+1e-9 and float(r['S_s'])*1000<=smax+1e-9]
        def key(r):return costs[r['point_id']]['energy_value_mJ'],float(r['L_s']),r['point_id']
        a=min(serial,key=key) if serial else None;b=min(task,key=key) if task else None
        row=dict(Lmax_ms=lmax,Smax_ms=smax,scope='HBM2_ONLY_known_energy_subset_not_global_choice',
            objective='MAC+DRAM energy separately, no area weighting; SRAM/static omitted.',
            timing_scope='Retained480-request curves; these energy-subset choices do not all have dedicated960 rechecks.')
        for prefix,r in (('serial',a),('task',b)):
            if r:
                row.update({prefix+'_'+k:r[k] for k in ('point_id','hardware_id','mode','dit_stages','dit_batching','L_s','S_s')})
                row.update({prefix+'_'+k:v for k,v in costs[r['point_id']].items() if k.startswith('energy_')})
        if a and b:
            x,y=costs[a['point_id']],costs[b['point_id']]
            delta=((y['MACs_per_req']-x['MACs_per_req'])*samples[:,keys.index('e_mac')]+
                (y['DRAM_bytes_per_req']-x['DRAM_bytes_per_req'])*8*samples[:,keys.index('e_dram_HBM2')])*1e-9
            row['MC_task_energy_lower_fraction']=float(np.mean(delta<-1e-12))
        rows.append(row)
    write_csv(ROOT/'paper/energy_selection_HBM2_only.csv',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('collect','selection','figures','parametric','energy'));a=p.parse_args()
    {'collect':collect,'selection':selection,'figures':figures,'parametric':parametric,'energy':energy}[a.action]()
