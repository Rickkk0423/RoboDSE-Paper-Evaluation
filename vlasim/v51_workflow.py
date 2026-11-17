"""V5.1 stage gates and frozen development/heldout/calibration preparation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0,str(Path(__file__).parent/'ramulator_bridge'))
from v51_catalog import catalog
from v5_audit import compare_values
from v5_protocol import digest,make_arrays,offered,write_json
from v4_replay_prepare import closed_prediction,difference,intersect,intervals,select_windows
from vlasim import DRAMModel,HWConfig,MapConfig,Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload
from case_v3_main import write_csv

ROOT=Path('results/v5_1')


def load(path):
    return json.loads(Path(path).read_text())


def stage1():
    source=ROOT/'stage1_input'
    frozen=load(source/'manifest.json')
    statuses=[]
    for i,item in enumerate(frozen['items']):
        path=ROOT/f'selfcheck_remote/shard_{i}/status.json'
        if not path.exists():
            path=ROOT/f'selfcheck_retry_remote/shard_{i}/status.json'
        row=load(path)
        if row['source_manifest_sha256']!=digest(source/'manifest.json') or row['config']!=item['config']:
            raise RuntimeError('HARD_STOP_frozen_selfcheck_input_changed')
        statuses.append(row)
        write_json(ROOT/'calib'/f'dram_v5_{row["id"]}_seq.json',row)
    a=load(ROOT/'equivalence_local_v2/equivalence.json')
    b=load(ROOT/'equivalence_remote/shard_0/equivalence.json')
    cross=compare_values(a['probes'],b['probes'])
    for label in ('seq_4KB','seq_64KB','seq_1024KB','W5_level1'):
        a=load(ROOT/'selfcheck_local/shard_2'/label/'result.json')
        b=load(ROOT/'selfcheck_remote/shard_2'/label/'result.json')
        cross+=compare_values(a['native'],b['native'],path=label)
    if cross:
        write_json(ROOT/'cross_host_failure.json',cross)
        raise RuntimeError('HARD_STOP_cross_host_difference_exceeds_1e-6')
    for label in ('seq_4KB','seq_64KB','seq_1024KB','W5_level1','W5_level2','HBM_full_period_BG'):
        a=load(ROOT/'selfcheck_retry_local/shard_7'/label/'result.json')
        b=load(ROOT/'selfcheck_retry_remote/shard_7'/label/'result.json')
        cross+=compare_values(a['native'],b['native'],path='HBM_'+label)
    if cross:
        write_json(ROOT/'cross_host_failure.json',cross)
        raise RuntimeError('HARD_STOP_cross_host_difference_exceeds_1e-6')
    if all(row['sampling']['level']==3 for row in statuses):
        raise RuntimeError('HARD_STOP_all_memory_W5_unverifiable')
    hbm=next(row for row in statuses if row['id']=='HBM2_c8')
    if not hbm['hbm_acceptance']['full_period_sampled_W5_completed']:
        raise RuntimeError('HBM full-period capacity acceptance incomplete')
    old=load('results/v5/delivery_manifest.json')
    changed=[n for n,h in old['artifacts_sha256'].items() if digest(Path('results/v5')/n)!=h]
    if changed:
        raise RuntimeError('V5 preserved artifacts changed '+str(changed))
    for name in ('NEXT_STEPS_V5.md','NEXT_STEPS_V5_1_AMENDMENT.md'):
        shutil.copy2(Path('/Users/mr.meeseeks/Downloads')/name,ROOT/name)
    gates=dict(status='running',spec='NEXT_STEPS_V5.md + NEXT_STEPS_V5_1_AMENDMENT.md',
        stage1=dict(status='pass_with_per_memory_fallback',cross_host='pass_10_probes_4_full_controls',
            memory_levels={r['id']:r['sampling'] for r in statuses},hbm_acceptance=hbm['hbm_acceptance'],
            original_v5_artifacts_verified=len(old['artifacts_sha256']),
            scope='All accepted controls audit native callbacks/read/write counts; '
                'low seq efficiency retains explicit failed mapper alternatives.'),
        stage2=dict(status='pending'),stage3=dict(status='pending'),stage4=dict(status='pending'),
        task=dict(status='preparation_only_no_measured_episodes',measured_episodes=0))
    write_json(ROOT/'gates.json',gates)
    write_csv(ROOT/'sampling_levels.csv',[dict(memory=r['id'],eta_seq=r['params']['eta_seq'],
        seq_gate=r['seq_gate'],level=r['sampling']['level'],block_bytes=r['sampling']['block_bytes'],
        levels=json.dumps(r['sampling']['levels']),capacity_GiB=r['geometry']['capacity_bytes']/2**30)
        for r in statuses])
    print('Stage1 complete:',[(r['id'],r['sampling']['level']) for r in statuses])


def memory_states():
    paths=[*(ROOT/'selfcheck_remote').glob('shard_*/status.json'),
           *(ROOT/'selfcheck_retry_remote').glob('shard_*/status.json')]
    rows=[load(p) for p in paths]
    return {row['id']:row for row in rows}


def qualified_windows(result,mode,k,*,two=False):
    lo,hi=result['measurement_window_s']
    v=intersect(intervals(result['timeline'],'vlm'),[(lo,hi)])
    d=intersect(intervals(result['timeline'],'dit'),[(lo,hi)])
    choices={'W1':difference(v,d)}
    if mode=='pipelined' and k==1:
        choices['W3']=intersect(v,d)
    if mode=='pipelined' and k>=2:
        choices['W4']=intersect(v,intersect(intervals(result['timeline'],'dit',2),[(lo,hi)]))
    windows=[];missing=[]
    for name in ('W1','W3','W4'):
        if name not in choices:
            missing.append(dict(window=name,reason='N/A for mode/k'))
            continue
        spans=[(a,b) for a,b in choices[name] if b-a>=.0005]
        if not spans:
            missing.append(dict(window=name,reason='no continuous qualifying 0.5ms steady interval'))
            continue
        for position in ((.25,.75) if two else (.5,)):
            a,b=spans[min(len(spans)-1,int(position*len(spans)))]
            start=(a+b-.0005)/2
            windows.append(dict(window=name,start_s=start,end_s=start+.0005,sampling=1,time_scale=1.))
    return windows,missing


def freeze_case(out,case,result,wl,selections,launches,block_bytes=None):
    tasks=[]
    for index,selection in enumerate(selections):
        arrays,regions,footprint=make_arrays(result,selection,wl,block_bytes=block_bytes or 2048)
        original=arrays['issue_ns']
        counts=[int(np.count_nonzero(arrays['core']==c))*64 for c in (0,1)]
        changes=max(1,int(np.count_nonzero(np.diff(arrays['core']))+1))
        # Offered-order interleave granularity follows the exact deterministic DMA merge.
        saturated=offered(arrays,'saturated',serial=case['mapping']['mode']=='serial')
        runs=max(1,int(np.count_nonzero(np.diff(saturated['core']))+1))
        for launch in launches:
            label=f'{case["id"]}_{selection["window"]}_{index}_{launch}'
            path=out/(label+'.npz')
            data=saturated if launch=='saturated' else offered(arrays,'open',serial=case['mapping']['mode']=='serial')
            np.savez_compressed(path,**data)
            finish=[];first=[]
            for c in (0,1):
                chosen=np.flatnonzero(arrays['core']==c)
                first.append(float(original[chosen[0]]) if len(chosen) else None)
                finish.append(float(original[chosen[-1]]+64/(case['peak_GBps']*case['params']['eta_seq']))
                              if len(chosen) else None)
            tasks.append(dict(id=label,path=path.name,sha256=digest(path),window=selection['window'],
                selection=selection,launch=launch,bg=case['bg'],bytes_by_stream=counts,
                params=case['params'],peak_GBps=case['peak_GBps'],standard=case['config']['standard'],
                interleave_bytes=sum(counts)/runs,source_event_interleave_bytes=sum(counts)/changes,
                open_finish_ns=finish,open_first_ns=first,regions=regions,footprint_bytes=footprint,
                sampling_block_bytes=block_bytes if selection['window']=='W5' else None,
                generation_config=dict(hardware=case['hardware'],mapping=case['mapping'])))
    return tasks


def prepare_development():
    if load(ROOT/'gates.json')['stage1']['status']!='pass_with_per_memory_fallback':
        raise RuntimeError('Stage1 not passed')
    out=ROOT/'development_input';out.mkdir(exist_ok=False)
    old=load('results/v4/p0a_input/manifest.json')
    wl=Pi05Workload();provider=NeuSimTiming('.native/compute',wl,allow_analytical_siglip=True)
    states=memory_states();items=[];unavailable=[]
    for row in old['cases']:
        cfg=row['config'];standard='HBM2' if cfg['memory']=='M-H256' else 'LPDDR5'
        config=dict(next(c for c in catalog() if c['standard']==standard))
        config.update(row['calibration']['backend_metadata']['config'])
        config['id']='V3_'+cfg['memory']
        case=dict(id=row['name'],config=config,hardware=cfg['hardware'],mapping=cfg['mapping'],
            params=row['calibration']['params'],bg=cfg['bg'],
            peak_GBps=cfg['hardware']['dram_bw']/1e9)
        result=Simulator(HWConfig(**case['hardware']),MapConfig(**case['mapping']),wl,
            DRAMModel(**case['params']),provider).run(120,24,record=True,diagnostics=True)
        windows,missing=qualified_windows(result,case['mapping']['mode'],case['mapping']['dit_stages'],two=True)
        windows=[w for w in windows if w['window'] in ('W3','W4')]
        unavailable.extend(dict(case=case['id'],**m) for m in missing if m['window'] in ('W3','W4'))
        tasks=freeze_case(out,case,result,wl,windows,('saturated',))
        items.append(dict(id=case['id'],config=config,tasks=tasks))
    for k in (1,2):
        for bg in (False,True):
            state=states['GDDR6_c16'];config=state['config']
            hw=HWConfig(n_cores=6,sram_mb=64,local_kb=2048,dram_bw=state['geometry']['peak_GBps']*1e9,
                        slice_mode=False,dram_priority=False)
            mp=MapConfig(vlm_cores=3 if k==1 else 4,dit_stages=k)
            params=dict(eta_seq=state['params']['eta_seq'],eta_mix=1.,prio_leak=0.)
            case=dict(id=f'GDDR_development_k{k}_{"bg" if bg else "plain"}',config=config,
                hardware=asdict(hw),mapping=asdict(mp),params=params,bg=bg,
                peak_GBps=state['geometry']['peak_GBps'])
            result=Simulator(hw,mp,wl,DRAMModel(**params),provider).run(120,24,record=True,diagnostics=True)
            windows,missing=qualified_windows(result,'pipelined',k,two=True)
            windows=[w for w in windows if w['window'] in ('W3','W4')]
            unavailable.extend(dict(case=case['id'],**m) for m in missing if m['window'] in ('W3','W4'))
            items.append(dict(id=case['id'],config=config,tasks=freeze_case(out,case,result,wl,windows,('saturated',))))
    references=[dict(path=str(p),sha256=digest(p)) for p in Path('results/v4/p0a_native').glob('shard_*/*.json')
                if ('_W3_saturated' in p.name or '_W4_saturated' in p.name)]
    write_json(out/'manifest.json',dict(items=items,unavailable=unavailable,v4_development=references,
        source_sha256=digest(__file__),
        scope='V4 saturated W3/W4 plus two distinct new times for every applicable original case; '
              'serial has no mixed window; k3 now uses >=2 active requests. '
              'Additional GDDR6 development is disjoint from heldout. '
              'GDDR source eta_mix=1 is an unfitted generation control, never a measured parameter.'))
    print('Frozen development',len(items),'configs',sum(len(i['tasks']) for i in items),'new windows')


def dev_samples():
    manifest=load(ROOT/'development_input/manifest.json');samples=[]
    for ref in manifest['v4_development']:
        if digest(ref['path'])!=ref['sha256']:
            raise RuntimeError('V4 development evidence changed')
        row=load(ref['path']);task=dict(row['window']);task['params']=dict(
            eta_seq=task['eta_seq'],eta_mix=task['eta_mix'],prio_leak=0.)
        task['standard']='HBM2' if task['memory']=='M-H256' else 'LPDDR5'
        with np.load(Path('results/v4/p0a_input')/task['trace']) as data:
            task['interleave_bytes']=sum(task['bytes_by_stream'])/max(1,np.count_nonzero(np.diff(data['core']))+1)
        samples.append(dict(task=task,result=dict(native=row['native'])))
    for path in (ROOT/'development_native').glob('shard_*/status.json'):
        status=load(path)
        if status['source_manifest_sha256']!=digest(ROOT/'development_input/manifest.json'):
            raise RuntimeError('frozen dev manifest changed')
        samples.extend(row for row in status['rows'] if 'result' in row)
    if len(list((ROOT/'development_native').glob('shard_*/status.json')))!=len(manifest['items']):
        raise RuntimeError('development shards incomplete')
    return samples


def predicted(task,eta):
    return closed_prediction(task['bytes_by_stream'],task['peak_GBps']*1e9,
        DRAMModel(eta_seq=task['params']['eta_seq'],eta_mix=eta))


def fit():
    samples=dev_samples();groups={}
    for sample in samples:
        key=sample['task']['standard']+('_bg' if sample['task']['bg'] else '_plain')
        groups.setdefault(key,[]).append(sample)
    params={};metrics=[];summary=[]
    for key,rows in sorted(groups.items()):
        def errors(p,form):
            values=[]
            for row in rows:
                task=row['task'];feature=np.log2(max(1.,task['interleave_bytes']/64))
                eta=float(np.exp(p[0]+(p[1]*feature if form=='B' else 0.)))
                prediction=predicted(task,eta)
                for c,(actual,estimate) in enumerate(zip(row['result']['native']['last_completion_ns'],prediction)):
                    if estimate is not None:
                        values.append(actual/estimate-1)
            return np.array(values)
        a=least_squares(lambda p:errors(p,'A'),[np.log(.9)],bounds=([np.log(.05)],[np.log(2.)]))
        b=least_squares(lambda p:errors(p,'B'),[a.x[0],0.],bounds=([np.log(.05),-1.],[np.log(2.),1.]))
        ea,eb=errors(a.x,'A'),errors(b.x,'B')
        params[key]=dict(A_eta_mix=float(np.exp(a.x[0])),B_eta_base=float(np.exp(b.x[0])),
            B_log2_slope=float(b.x[1]),A_mean_absolute_error=float(np.mean(np.abs(ea))),
            A_max_absolute_error=float(np.max(np.abs(ea))),B_mean_absolute_error=float(np.mean(np.abs(eb))),
            B_max_absolute_error=float(np.max(np.abs(eb))),samples=len(rows))
    a_ok=all(p['A_max_absolute_error']<=.05 for p in params.values())
    b_ok=all(p['B_max_absolute_error']<=.05 for p in params.values())
    # Prefer the simpler constant when neither form clears the requested development gate.
    # A failed development gate is reported, never repaired using heldout data.
    chosen='B' if b_ok and not a_ok else 'A'
    for key,rows in sorted(groups.items()):
        p=params[key]
        for row in rows:
            task=row['task'];feature=np.log2(max(1.,task['interleave_bytes']/64))
            eta=p['A_eta_mix'] if chosen=='A' else p['B_eta_base']*np.exp(p['B_log2_slope']*feature)
            prediction=predicted(task,eta)
            for c,(actual,estimate) in enumerate(zip(row['result']['native']['last_completion_ns'],prediction)):
                if estimate is not None:
                    metrics.append(dict(id=task['id'],standard=task['standard'],bg=task['bg'],window=task['window'],
                        launch='saturated',stream=('vlm','dit')[c],eta_mix=eta,actual_ns=actual,predicted_ns=estimate,
                        signed_error_pct=(actual/estimate-1)*100,absolute_error_pct=abs(actual/estimate-1)*100))
    write_json(ROOT/'model_fit.json',dict(chosen_form=chosen,groups=params,A_dev_gate=a_ok,B_dev_gate=b_ok,
        selection_reason='B only if it alone clears every development error <=5%; otherwise fewer-parameter A. '
            'If neither passes, retain failed model status and evaluate untouched heldout for dual-model classification.',
        development_manifest_sha256=digest(ROOT/'development_input/manifest.json'),
        model_B_feature='log2(mean contiguous logical DMA bytes per stream run / 64), derived from exact fluid-generated '
                        'source demand counts and deterministic saturation merge.'))
    write_csv(ROOT/'development_metrics.csv',metrics)
    print('Selected',chosen,'A_gate',a_ok,'B_gate',b_ok)


def prepare_heldout():
    fitted=load(ROOT/'model_fit.json');states=memory_states()
    out=ROOT/'heldout_input';out.mkdir(exist_ok=False)
    wl=Pi05Workload();provider=NeuSimTiming('.native/compute',wl,allow_analytical_siglip=True)
    specs=[('HBM2_c8',1,6,False),('HBM2_c8',2,7,True),('LPDDR5_c16',1,5,False),
           ('LPDDR5_c16',2,8,True),('LPDDR5_c16',3,7,False),('GDDR6_c16',1,6,False),
           ('GDDR6_c16',2,5,True),('HBM2_c8',3,8,True)]
    items=[];unavailable=[]
    if fitted['chosen_form']!='A':
        raise RuntimeError('Form B requires per-allocation DMA implementation before heldout execution')
    for i,(memory,k,split,bg) in enumerate(specs):
        state=states[memory];config=state['config'];group=config['standard']+('_bg' if bg else '_plain')
        params=dict(eta_seq=state['params']['eta_seq'],eta_mix=fitted['groups'][group]['A_eta_mix'],prio_leak=0.)
        hw=HWConfig(n_cores=12,sram_mb=32,local_kb=512,dram_bw=state['geometry']['peak_GBps']*1e9,
            slice_mode=False,dram_priority=False)
        mp=MapConfig(vlm_cores=split,dit_stages=k)
        case=dict(id=f'heldout_{i}_{memory}_k{k}',config=config,hardware=asdict(hw),mapping=asdict(mp),
                  params=params,bg=bg,peak_GBps=state['geometry']['peak_GBps'])
        result=Simulator(hw,mp,wl,DRAMModel(**params),provider).run(120,24,record=True,diagnostics=True)
        windows,missing=qualified_windows(result,'pipelined',k)
        if state['sampling']['level']!=3:
            windows.append(next(w for w in select_windows(result,'pipelined',k)[0] if w['window']=='W5'))
        else:
            missing.append(dict(window='W5',reason='memory sampling ladder level3: W5 unverified'))
        missing.append(dict(window='W2',reason='N/A: no pure DiT interval in pipeline protocol'))
        unavailable.extend(dict(case=case['id'],**m) for m in missing)
        tasks=freeze_case(out,case,result,wl,windows,('open','saturated'),state['sampling']['block_bytes'])
        items.append(dict(id=case['id'],config=config,hardware=asdict(hw),mapping=asdict(mp),
            bg=bg,params=params,mapper=state['mapper'],tasks=tasks))
    frozen=dict(items=items,unavailable=unavailable,fit_sha256=digest(ROOT/'model_fit.json'),
        source_sha256=digest(__file__),freeze_rule='All 8 new hardware/mapping identities, source windows/times, '
            'trace hashes and parameters frozen before any heldout native execution. No heldout fitting.',
        novelty='12 cores, 32 MB shared, 512 KB private: no V3/V4 executed replay identity used this hardware. '
                'GDDR6 and large-HBM organization also have new native identities.')
    write_json(out/'manifest.json',frozen)
    write_json(ROOT/'heldout_manifest.json',frozen)
    print('Frozen heldout',len(items),'configs',sum(len(i['tasks']) for i in items),'traces')


def heldout_gate():
    frozen=load(ROOT/'heldout_manifest.json');rows=[];unavailable=list(frozen['unavailable'])
    paths=list((ROOT/'heldout_native').glob('shard_*/status.json'))
    if len(paths)!=8 or digest(ROOT/'heldout_input/manifest.json')!=digest(ROOT/'heldout_manifest.json'):
        raise RuntimeError('incomplete or changed heldout freeze')
    for path in paths:
        status=load(path)
        if status['source_manifest_sha256']!=digest(ROOT/'heldout_manifest.json'):
            raise RuntimeError('heldout manifest changed')
        for record in status['rows']:
            task=record['task']
            if 'result' not in record:
                unavailable.append(dict(case=status['id'],window=task['window'],reason=record['reason']))
                continue
            native=record['result']['native']
            prediction=predicted(task,task['params']['eta_mix']) if task['launch']=='saturated' else task['open_finish_ns']
            first=[0.,0.] if task['launch']=='saturated' else task['open_first_ns']
            for c,estimate in enumerate(prediction):
                if estimate is None:
                    continue
                actual=native['last_completion_ns'][c]-native['first_offer_ns'][c]
                expected=estimate-first[c]
                rows.append(dict(id=task['id'],case=status['id'],standard=task['standard'],bg=task['bg'],
                    launch=task['launch'],window=task['window'],stream=('vlm','dit')[c],actual_duration_ns=actual,
                    predicted_duration_ns=expected,signed_error_pct=(actual/expected-1)*100,
                    absolute_error_pct=abs(actual/expected-1)*100))
    sat=[r for r in rows if r['launch']=='saturated']
    mean=float(np.mean([r['absolute_error_pct'] for r in sat]));worst=max(r['absolute_error_pct'] for r in sat)
    passed=worst<=10 and mean<=5
    bg=[r for r in sat if r['bg']]
    bg_pass=bool(bg) and max(r['absolute_error_pct'] for r in bg)<=10 and np.mean([r['absolute_error_pct'] for r in bg])<=5
    gate=dict(status='pass' if passed else 'dual_model',mean_error_pct=mean,max_error_pct=worst,
        dram_model_mode='V5_primary' if passed else 'dual_model_DRAM_unvalidated' if mean>10 else 'dual_model',
        bg_main=bool(bg_pass),saturated_flow_measurements=len(sat),all_flow_measurements=len(rows),
        unavailable=unavailable,heldout_manifest_sha256=digest(ROOT/'heldout_manifest.json'),
        prohibition='No parameter updates from heldout, including after failure.')
    write_json(ROOT/'heldout_gate.json',gate);write_csv(ROOT/'heldout_metrics.csv',rows)
    gates=load(ROOT/'gates.json');gates['stage2']=gate;write_json(ROOT/'gates.json',gates)
    print('Heldout:',gate['dram_model_mode'],mean,worst)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage1','prepare-dev','fit','prepare-heldout','heldout-gate'))
    args=parser.parse_args()
    {'stage1':stage1,'prepare-dev':prepare_development,'fit':fit,
     'prepare-heldout':prepare_heldout,'heldout-gate':heldout_gate}[args.action]()
