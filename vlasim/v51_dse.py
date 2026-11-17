"""Resumable periodic-only wide DSE using audited unchanged operation templates."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict,replace
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np

from case_v3_main import write_csv
from v4_scheduler import observed_nonmonotonic,periodic_gate,search_period
from v51_fast import Periodic,build
from v51_workflow import ROOT,load
from v5_protocol import digest,write_json
from vlasim import DRAMModel,HWConfig,MapConfig,Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload

CORES=(1,2,3,4,6,8,12,16)
FACTORS=(1.,1.1,1.25,1.5,2.)


def lower_bound(hw,mp,wl):
    fv,wv=wl.vlm_totals();fd,wd=wl.dit_totals_per_request()
    if mp.mode=='serial':
        return max((fv+fd)/hw.peak,(wv+wd)/hw.dram_bw)
    k=mp.dit_stages if mp.dit_batching else 1
    return max(fv/(hw.core_peak*mp.vlm_cores),fd/(hw.core_peak*(hw.n_cores-mp.vlm_cores)),
               (wv+wd/k)/hw.dram_bw)


def semantic_key(engine):
    parts=[bytes(engine.v),bytes(engine.d),bytes(engine.offsets),bytes(engine.lengths),
        json.dumps(dict(k=engine.k,serial=engine.mp.mode=='serial',bw=engine.hw.dram_bw,
            eta_seq=engine.dram.eta_seq,eta_mix=engine.dram.eta_mix,
            policy=engine.mp.bw_policy,partition=engine.mp.stream_partition),sort_keys=True).encode()]
    return hashlib.sha256(b''.join(parts)).hexdigest()


def summarize(result,period,k):
    gate=periodic_gate(result,period,k)
    lo,hi=result['measurement_window_s']
    rounds=[r for r in result['dit_rounds'] if r['start_s']>=lo and r['end_s']<=hi and not r['tail_drain']]
    metrics={key:result[key] for key in ('dit_GB_per_req','dram_GB_per_req','vlm_busy','dit_busy',
        'steady_vlm_busy','steady_dit_busy','steady_KV_GBps','steady_vlm_GBps','steady_dit_GBps',
        'kv_on_chip','act_on_chip','sram_ok')}
    metrics.update(steady_dit_GB_per_req=result['steady_dit_GBps']*period,
        steady_dram_GB_per_req=(result['steady_vlm_GBps']+result['steady_dit_GBps'])*period,
        steady_KV_GB_per_req=result['steady_KV_GBps']*period)
    for key in ('duration_s','compute_s','exposed_memory_s','linear_s','attention_s','wait_before_s'):
        metrics['round_'+key]=float(np.mean([r[key] for r in rounds])) if rounds else None
    metrics['steady_rounds']=len(rounds)
    return dict(gate=gate,metrics=metrics)


def evaluate(engine,path):
    if (path/'status.json').exists():
        saved=load(path/'status.json')
        if saved['raw_sha256']!=digest(path/'requests.npz'):
            raise RuntimeError('HARD_STOP_DSE_checkpoint_hash_mismatch')
        return saved
    path.mkdir(parents=True,exist_ok=True)
    raw_requests=[];trial_times=[];curve_rounds=[]
    def trial(t,n=480,curve=False):
        result=engine.run(t,n)
        trial_times.append(t)
        raw_requests.append(np.array([[r[key] for key in ('obs_s','vlm_start_s','vlm_end_s','done_s')]
            for r in result['requests']]))
        if curve:
            curve_rounds.append(np.array([[r[key] for key in ('start_s','end_s','duration_s','compute_s',
                'exposed_memory_s','linear_s','attention_s','dram_bytes','weight_bytes','wait_before_s',
                'stage_mask','tail_drain')] for r in result['dit_rounds']]))
        return summarize(result,t,engine.k)
    initial=lower_bound(engine.hw,engine.mp,engine.wl)
    search=search_period(lambda t:trial(t)['gate'],upper=max(.0001,initial*1.3),cap=30.)
    curve=[]
    if search['Tmin_s'] is not None:
        for factor in FACTORS:
            t=search['Tmin_s']*factor
            curve.append(dict(factor=factor,T_s=t,**trial(t,curve=True)))
    np.savez_compressed(path/'requests.npz',period_s=np.array(trial_times),requests=np.stack(raw_requests),
        **{f'curve_rounds_{i}':r for i,r in enumerate(curve_rounds)})
    result=dict(search=search,nonmonotonic=observed_nonmonotonic(search['trials']),curve=curve,
        raw_sha256=digest(path/'requests.npz'),raw_schema='Every search and curve trial: [obs,VLMstart,VLMend,done] '
            'for all 480 requests; each curve has all raw DiT round times/bytes/masks/tail flags.',
        requests=480,engine='v51-periodic-template-kernel',source_sha256=digest(Path(__file__)))
    result=json.loads(json.dumps(result))
    write_json(path/'status.json',result)
    return result


def run_shard(task):
    memory,cores,root,snapshot=task
    root=Path(root);out=root/'shards'/f'{memory}_c{cores}'
    if (out/'status.json').exists():
        return load(out/'status.json')
    out.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    calibration=load(ROOT/'calibration.json')[memory];gate=load(ROOT/'heldout_gate.json')
    wl=Pi05Workload();provider=NeuSimTiming(snapshot,wl,allow_analytical_siglip=True)
    library=root/('periodic.dylib' if __import__('sys').platform=='darwin' else 'periodic.so')
    models=('v51','v3_form') if gate['status']=='dual_model' else ('v51',)
    records=[];curves=[];ablations=[];rechecks=[]
    mappings=[MapConfig(mode='serial',vlm_cores=cores)]
    mappings += [MapConfig(vlm_cores=split,dit_stages=k,dit_batching=batch)
        for split in range(1,cores) for k,batch in ((1,True),(2,True),(3,True),(2,False),(3,False))]
    for shared in (8,16,32,64):
        for model,track,policy,bg in itertools.product(models,('neusim_unsliced','analytical_sliced'),
                                                     ('fair','vlm_priority'),(False,True)):
            key=('legacy_bg' if bg else 'legacy_plain') if model=='v3_form' else ('vla_bg' if bg else 'vla_plain')
            params=calibration['baseline']['bg' if bg else 'plain']['params'] if model=='v3_form' else calibration['params'][key]
            dram=DRAMModel(**params,version=f'V5.1_{memory}_{key}')
            hw=HWConfig(n_cores=cores,sram_mb=shared,local_kb=512,
                dram_bw=calibration['geometry']['peak_GBps']*1e9,slice_mode=track=='analytical_sliced',
                dram_priority=False)
            context=dict(memory=memory,n_cores=cores,sram_mb=shared,model=model,track=track,
                bw_policy=policy,bg=bg,scenario='main' if policy=='fair' and (not bg or gate['bg_main']) else 'unvalidated_scenario',
                W5_status=calibration['sampling']['status'],calibration_version=dram.version,
                model_status=gate['dram_model_mode'],cost_status='placeholder_not_calibrated')
            context['baseline_scope']=calibration['baseline']['bg' if bg else 'plain']['scope'] if model=='v3_form' else 'new_VLA_layout_native_fit'
            best=float('inf');context_curves=[]
            for base in sorted(mappings,key=lambda m:lower_bound(hw,m,wl)):
                mp=replace(base,bw_policy=policy,vlm_launch='periodic',launch_period_s=1.)
                bound=lower_bound(hw,mp,wl)
                identity={**context,**asdict(mp)}
                # local SRAM is currently feasibility-only; timing templates do not depend on it.
                engine=Periodic(hw,mp,wl,dram,provider if track=='neusim_unsliced' else None,library)
                uid=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
                row={**identity,'config_id':uid,'lower_bound_s':bound,'kv_on_chip_requested':mp.kv_on_chip,
                    'kv_on_chip':engine.reference.kv_on_chip,'act_on_chip':engine.reference.act_on_chip,
                    'private_sram_semantics':'feasibility_only_not_timing_calibrated'}
                if not engine.reference.sram_ok:
                    row.update(status='static_pruned',reason='SRAM feasibility failed')
                elif bound>1.2*best:
                    row.update(status='lower_bound_pruned',reason='LB > 1.2 * best observed Tmin in same context',
                        incumbent_Tmin_s=best)
                else:
                    semantic=semantic_key(engine);path=out/'evaluations'/semantic
                    result=evaluate(engine,path)
                    row.update(status=result['search']['status'],Tmin_s=result['search']['Tmin_s'],
                        bracket_width_s=result['search'].get('bracket_width_s'),semantic_id=semantic,
                        raw=str((path/'requests.npz').relative_to(ROOT)),raw_sha256=result['raw_sha256'],
                        observed_nonmonotonic=result['nonmonotonic'])
                    if row['Tmin_s'] is not None:
                        best=min(best,row['Tmin_s'])
                    for point in result['curve']:
                        entry={**row,**point['metrics'],'factor':point['factor'],'T_s':point['T_s'],
                            'L_s':point['gate']['L_mean_s'],'S_s':point['gate']['S_mean_s'],
                            'curve_gate':point['gate']['pass_gate']}
                        curves.append(entry);context_curves.append((entry,engine))
                    if result['curve']:
                        row.update(result['curve'][0]['metrics'])
                        for point in result['curve']:
                            row[f'L_factor_{point["factor"]}_s']=point['gate']['L_mean_s']
                records.append(row)
            # Recheck each nondominated (L,S) member with the original Python scheduler at 960 requests.
            frontier=[]
            for row,engine in sorted(context_curves,key=lambda p:(p[0]['S_s'],p[0]['L_s'])):
                if not row['curve_gate'] or not row['dit_batching']:
                    continue
                if frontier and row['L_s']>=min(p[0]['L_s'] for p in frontier)-1e-12:
                    continue
                frontier.append((row,engine))
            for row,engine in frontier:
                checkpoint=out/'rechecks'/(row['semantic_id']+f'_{row["T_s"]:.17g}.json.gz')
                if checkpoint.exists():
                    with gzip.open(checkpoint,'rt') as stream:
                        audit=json.load(stream)['audit']
                    audit=dict(audit,source_config_id=audit['config_id'],config_id=row['config_id'],
                        exact_semantic_reuse=True)
                else:
                    reference=Simulator(hw,replace(engine.mp,launch_period_s=row['T_s']),wl,dram,
                        provider if track=='neusim_unsliced' else None).run(960,192,diagnostics=True)
                    fast=engine.run(row['T_s'],960)
                    if len(reference['requests'])!=len(fast['requests']):
                        raise RuntimeError('HARD_STOP_frontier_reference_count_mismatch')
                    error=max(abs(a['done_s']-b['done_s']) for a,b in zip(reference['requests'],fast['requests']))
                    if error>1e-6:
                        raise RuntimeError('HARD_STOP_frontier_reference_difference_exceeds_1e-6')
                    check=periodic_gate(reference,row['T_s'],engine.k)
                    audit=dict(config_id=row['config_id'],factor=row['factor'],reference_max_done_error_s=error,
                        gate=check,initial_L_s=row['L_s'],initial_S_s=row['S_s'],requests=960)
                    checkpoint.parent.mkdir(exist_ok=True)
                    with gzip.open(checkpoint,'wt') as stream:
                        json.dump(dict(audit=audit,requests=reference['requests'],dit_rounds=reference['dit_rounds']),stream)
                rechecks.append(audit)
            if track=='neusim_unsliced' and policy=='fair':
                candidates=[r for r,e in context_curves if r['mode']=='pipelined' and r['dit_batching']
                    and r['factor']==1. and r['curve_gate']]
                if candidates:
                    selected=min(candidates,key=lambda r:(r['Tmin_s'],r['L_s'],r['config_id']))
                    for base in mappings:
                        if base.mode!='pipelined' or base.vlm_cores!=selected['vlm_cores']:
                            continue
                        mp=replace(base,bw_policy=policy,vlm_launch='periodic',launch_period_s=1.)
                        engine=Periodic(hw,mp,wl,dram,provider,library)
                        semantic=semantic_key(engine);result=evaluate(engine,out/'evaluations'/semantic)
                        entry={**context,**asdict(mp),'phase':'same_split_control_not_optimization',
                            'selected_split':selected['vlm_cores'],'status':result['search']['status'],
                            'Tmin_s':result['search']['Tmin_s'],'semantic_id':semantic,
                            'pruning_scope':'Required ablation control, independently executed even when optimization-pruned.'}
                        if result['curve']:
                            point=result['curve'][0]
                            entry.update(point['metrics'],L_s=point['gate']['L_mean_s'],S_s=point['gate']['S_mean_s'],
                                curve_gate=point['gate']['pass_gate'])
                        ablations.append(entry)
                else:
                    ablations.append(dict(**context,status='N/A_no_feasible_pipeline_allocation',
                        phase='same_split_control_not_optimization'))
    # Expand only exact private-SRAM timing equivalence, retaining both physical identities.
    def expand(rows):
        return [dict(row,local_kb=local,hardware_id=f'{memory}_c{cores}_s{row["sram_mb"]}_p{local}')
            for row in rows for local in (512,2048)]
    write_csv(out/'hw_grid.csv',expand(records));write_csv(out/'curves.csv',expand(curves))
    write_csv(out/'k_ablation.csv',expand(ablations))
    write_json(out/'rechecks.json',rechecks)
    status=dict(memory=memory,cores=cores,rows=len(records)*2,curve_rows=len(curves)*2,
        reference_rechecks=len(rechecks),wall_seconds=time.monotonic()-started,
        hashes={name:digest(out/name) for name in ('hw_grid.csv','curves.csv','k_ablation.csv','rechecks.json')})
    write_json(out/'status.json',status);print('DSE shard completed',memory,cores,status['rows'],flush=True)
    return status


def run(workers=4):
    root=ROOT/'dse';root.mkdir(exist_ok=True)
    started=time.time()
    validation=load(ROOT/'fast_validation/local/status.json')
    if not validation['passed']:
        raise RuntimeError('Long-sequence kernel validation required')
    if validation['source_sha256']!=digest(Path('vlasim/v51_periodic.cpp')) or validation['wrapper_sha256']!=digest(Path('vlasim/v51_fast.py')):
        raise RuntimeError('Validated kernel/wrapper source changed')
    if not (ROOT/'fast_validation/cross_host.json').exists():
        raise RuntimeError('Cross-host kernel validation required')
    if not load(ROOT/'fast_validation/cross_host.json')['passed']:
        raise RuntimeError('HARD_STOP_cross_host_kernel_validation_failed')
    build(root)
    calibrations=load(ROOT/'calibration.json')
    manifest=dict(calibration_sha256=digest(ROOT/'calibration.json'),heldout_gate_sha256=digest(ROOT/'heldout_gate.json'),
        sources_sha256={p.name:digest(p) for p in (Path(__file__),Path('vlasim/v51_fast.py'),Path('vlasim/v51_periodic.cpp'))},
        cores=CORES,shared_MB=[8,16,32,64],private_KB=[512,2048],factors=FACTORS,
        request_count=480,frontier_reference_requests=960,resolution_s=.0001,
        pruning='Separate model/compute-track/policy/layout contexts; failed search points retained.',
        BG_scope='Bankgroup isolation fit; all channels shared, NOT a fixed half-channel bandwidth partition.',
        private_SRAM_scope='512/2048KB exact timing reuse: existing compute provider ignores private capacity beyond feasibility.')
    manifest=json.loads(json.dumps(manifest))
    if (root/'manifest.json').exists() and load(root/'manifest.json')!=manifest:
        raise RuntimeError('DSE frozen manifest changed; use new output instead of overwriting')
    write_json(root/'manifest.json',manifest)
    execution=dict(status='running',host=__import__('socket').gethostname(),workers=workers,
        started_unix_s=started,command=f'PYTHONPATH=vlasim .venv/bin/python vlasim/v51_dse.py --workers {workers}',
        frozen_manifest_sha256=digest(root/'manifest.json'))
    write_json(ROOT/'execution/dse_local.json',execution)
    order=sorted(calibrations,key=lambda s:({'LPDDR5':0,'GDDR6':1,'HBM2':2}[s.split('_')[0]],int(s.split('c')[-1])))
    snapshot=str(Path('.native/compute').resolve())
    for standard in ('LPDDR5','GDDR6','HBM2'):
        tasks=[(m,c,str(root),snapshot) for m in order if m.startswith(standard) for c in CORES]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(run_shard,t) for t in tasks]):
                try:
                    future.result()
                except Exception as error:
                    execution.update(status='stopped',exception_type=type(error).__name__,reason=str(error),
                        stopped_unix_s=time.time())
                    write_json(ROOT/'execution/dse_local.json',execution)
                    if 'HARD_STOP' in str(error):
                        write_json(ROOT/'hard_stop.json',execution)
                    for process in pool._processes.values():
                        process.terminate()
                    raise
        write_json(root/f'{standard}_completed.json',dict(memories=[m for m in order if m.startswith(standard)],
            hardware_points=len(tasks)*8,source_sha256=digest(__file__)))
    execution.update(status='completed',finished_unix_s=time.time(),wall_seconds=time.time()-started)
    write_json(ROOT/'execution/dse_local.json',execution)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();run(a.workers)
