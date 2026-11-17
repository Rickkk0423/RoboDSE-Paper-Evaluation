"""Independent audits and summaries of V6 native and empirical stress evidence."""
import argparse
from collections import defaultdict
from pathlib import Path
import shutil
import sys

import numpy as np

from v6_common import ROOT,load,write_json,write_csv,digest
from v51_package import read_csv


def native():
    sys.path.insert(0,str(Path(__file__).parent/'ramulator_bridge'))
    from v51_catalog import check_accounting
    rows=[]
    for stage in ('seq','repair'):
        source=ROOT/(stage+'_input');manifest=load(source/'manifest.json')
        for i,item in enumerate(manifest['items']):
            directory=ROOT/f'{stage}_native/shard_{i}'
            status=load(directory/'status.json')
            if status['source_manifest_sha256']!=digest(source/'manifest.json'):
                raise RuntimeError('HARD_STOP_native_manifest')
            for entry in status['rows']:
                if 'result' not in entry:
                    rows.append(dict(stage=stage,shard=i,task=entry['task']['id'],status=entry['status']))
                    continue
                task=entry['task'];result=entry['result'];n=result['native']
                if not result['accounting']['passed'] or n['accepted']!=n['completed']:
                    raise RuntimeError('HARD_STOP_native_accounting')
                if digest(source/task['path'])!=result['trace_sha256']:
                    raise RuntimeError('HARD_STOP_native_trace')
                for name,sha in result['stats_sha256'].items():
                    if digest(directory/task['id']/name)!=sha:
                        raise RuntimeError('HARD_STOP_native_stats')
                counts=load(directory/task['id']/'manifest.json')['counts']
                check_accounting(n,[directory/task['id']/name for name in result['stats_sha256']],counts)
                rows.append(dict(stage=stage,shard=i,task=task['id'],status='passed',
                    accepted=n['accepted'],completed=n['completed'],logical_bytes=n['logical_bytes'],
                    status_sha256=digest(directory/'status.json')))
    differences=[]
    for index in (1,91):
        local=load(ROOT/f'seq_local/shard_{index}/status.json');remote=load(ROOT/f'seq_native/shard_{index}/status.json')
        if len(local['rows'])!=len(remote['rows']):raise RuntimeError('HARD_STOP_crosshost_count')
        for a,b in zip(local['rows'],remote['rows']):
            x,y=a['result']['native'],b['result']['native']
            for key in ('accepted','completed','cycles','logical_bytes','stream_transactions',
                        'first_completion_ns','last_completion_ns'):
                if isinstance(x[key],list):
                    delta=max([abs(v-w) for v,w in zip(x[key],y[key]) if v is not None and w is not None] or [0.])
                    if any((v is None)!=(w is None) for v,w in zip(x[key],y[key])):
                        raise RuntimeError('HARD_STOP_crosshost_null')
                else:
                    delta=abs(x[key]-y[key])
                differences.append(dict(identity=local['item']['id'],task=a['task']['id'],field=key,max_absolute_difference=delta))
    if max(r['max_absolute_difference'] for r in differences)>1e-6:
        raise RuntimeError('HARD_STOP_crosshost_difference')
    write_csv(ROOT/'validation/native_audit.csv',rows)
    write_json(ROOT/'validation/native_audit.json',dict(passed=True,rows=len(rows),
        completed=sum(r['status']=='passed' for r in rows),crosshost=differences,
        crosshost_scope='GDDR6_c16 and HBM2_c32 aggregate q8192, all three original seq traces each, local macOS vs einstein Linux.'))


def band():
    manifest=load(ROOT/'band/manifest.json');inputs=read_csv(ROOT/'band/inputs.csv')
    if digest(ROOT/'band/inputs.csv')!=manifest['input_sha256']:
        raise RuntimeError('HARD_STOP_band_inputs')
    correction=load(ROOT/'band/control_repair/manifest.json')
    if correction['input_sha256']!=digest(ROOT/'band/inputs.csv') or correction['source_sha256']!=digest('vlasim/v6_control_band.py'):
        raise RuntimeError('HARD_STOP_corrected_control_source')
    initial=ROOT/'band/initial_summary'
    if not initial.exists():
        initial.mkdir()
        for name in ('intervals.csv','audit.json'):
            if (ROOT/'band'/name).exists():shutil.copy2(ROOT/'band'/name,initial/name)
    summaries=[];totals=defaultdict(int)
    for path in sorted((ROOT/'band/shards').glob('*/status.json')):
        directory=path.parent;status=load(path)
        fixed=ROOT/'band/control_repair/shards'/directory.name
        fixedstatus=load(fixed/'status.json');groups=defaultdict(list);effective_rows=0
        for layer,state,corrected in ((directory,status,False),(fixed,fixedstatus,True)):
            for name,sha in state['hashes'].items():
                if digest(layer/name)!=sha:raise RuntimeError('HARD_STOP_band_hash')
            with np.load(layer/'requests.npz') as data:
                raw=data['requests']
                if raw.shape!=(state['unique_runs'],480,4) or not np.isfinite(raw).all():raise RuntimeError('HARD_STOP_band_raw_shape_or_finite')
                if (np.diff(raw,axis=2)<-1e-9).any() or (np.diff(raw[:,:,0],axis=1)<0).any():raise RuntimeError('HARD_STOP_band_request_order')
            runs=read_csv(layer/'runs.csv')
            if len(runs)!=state['rows']:raise RuntimeError('HARD_STOP_band_row_count')
            retained=runs if corrected else [r for r in runs if r['band_role']!='same_allocation_control']
            checked={};used=set()
            for row in retained:
                idx=int(row['raw_index']);used.add(idx)
                if not 0<=idx<state['unique_runs']:raise RuntimeError('HARD_STOP_band_raw_index')
                groups[int(row['input_index'])].append(row);effective_rows+=1
                k=1 if row['mode']=='serial' else int(row['dit_stages']);key=idx,k
                if key not in checked:
                    stop=480-k-2
                    checked[key]=(float(np.mean(raw[idx,96:stop,3]-raw[idx,96:stop,0])),float(np.mean(np.diff(raw[idx,95:stop,3]))))
                if not np.allclose(checked[key],[float(row['L_s']),float(row['S_s'])],rtol=0,atol=1e-8):raise RuntimeError('HARD_STOP_band_LS_reconciliation')
            totals['unique_runs']+=len(used)
            totals['archived_runs_including_superseded']+=state['unique_runs']
        if effective_rows!=status['rows']:raise RuntimeError('HARD_STOP_band_corrected_coverage')
        original=[r for r in inputs if r['memory']==status['memory'] and int(r['n_cores'])==status['cores']]
        if len(original)!=status['input_rows'] or len(groups)!=len(original):
            raise RuntimeError('HARD_STOP_band_coverage')
        for index,values in groups.items():
            passed=[r for r in values if r['pass_gate']=='True'];base=original[index]
            summaries.append(dict(memory=status['memory'],n_cores=status['cores'],
                hardware_id=base['hardware_id'],config_id=base['config_id'],period_s=base['period_s'],
                band_role=base['band_role'],model=base['model'],track=base['track'],bg=base['bg'],
                evidence_directory=str(fixed if base['band_role']=='same_allocation_control' else directory),
                scenarios=len(values),stable_scenarios=len(passed),stable_fraction=len(passed)/len(values),
                upper_bound_unbounded=len(passed)!=len(values),
                finite_L_min_s=min((float(r['L_s']) for r in passed),default=None),
                finite_L_max_s=max((float(r['L_s']) for r in passed),default=None),
                finite_S_min_s=min((float(r['S_s']) for r in passed),default=None),
                finite_S_max_s=max((float(r['S_s']) for r in passed),default=None),
                interval_scope='Finite stable subset only; any failed gate makes full steady upper bound unbounded.'))
        totals['shards']+=1;totals['input_rows']+=len(original)
        totals['scenario_rows']+=effective_rows
    if totals['shards']!=80 or totals['input_rows']!=manifest['rows']:
        raise RuntimeError('HARD_STOP_band_missing_shards')
    write_csv(ROOT/'band/intervals.csv',summaries)
    write_json(ROOT/'band/audit.json',dict(passed=True,**totals,
        fully_stable_inputs=sum(not r['upper_bound_unbounded'] for r in summaries),
        partially_or_fully_unstable_inputs=sum(r['upper_bound_unbounded'] for r in summaries),
        frontier_inputs=sum(r['band_role']=='frozen_frontier' for r in summaries),
        inputs_sha256=digest(ROOT/'band/inputs.csv'),intervals_sha256=digest(ROOT/'band/intervals.csv'),
        superseded_control_inputs=11200,corrected_control_shards=80,
        correction='Original frozen frontiers retained; all blank-ID same-allocation controls replaced by semantic-key reruns. Initial raw evidence retained.',
        scope='Empirical stress scenarios, not confidence bounds or probability estimates.'))
    print(dict(totals),flush=True)


def dse():
    manifest=load(ROOT/'dse/manifest.json')
    for name,sha in manifest['sources_sha256'].items():
        if digest(name)!=sha:raise RuntimeError('HARD_STOP_DSE_source_changed')
    for name,key in (('calibration.json','calibration_sha256'),('heldout_gate.json','heldout_gate_sha256')):
        if digest(ROOT/name)!=manifest[key]:raise RuntimeError('HARD_STOP_DSE_input_changed')
    if len(list((ROOT/'dse/shards').glob('*/status.json')))!=manifest['expected_shards']:
        raise RuntimeError('DSE archive incomplete')
    paths=[*(ROOT/'dse/shards').glob('*/evaluations/*/status.json'),
        *(ROOT/'dse/ablation_supplement/evaluations').glob('*/status.json')]
    rows=[];round_count=0
    for path in paths:
        status=load(path);raw=path.parent/'requests.npz'
        if digest(raw)!=status['raw_sha256'] or status['source_sha256']!=digest('vlasim/v51_dse.py'):
            raise RuntimeError('HARD_STOP_DSE_raw_or_source')
        with np.load(raw) as data:
            requests=data['requests']
            if requests.shape[1:]!=(480,4) or len(requests)!=len(data['period_s']) or not np.isfinite(requests).all():
                raise RuntimeError('HARD_STOP_DSE_raw_shape')
            if (np.diff(requests,axis=2)<-1e-8).any():raise RuntimeError('HARD_STOP_DSE_request_order')
            for index,point in enumerate(status['curve']):
                rounds=data['curve_rounds_'+str(index)];round_count+=len(rounds)
                if not np.isfinite(rounds).all():raise RuntimeError('HARD_STOP_DSE_nonfinite_round')
                for total in (rounds[:,3]+rounds[:,4],rounds[:,5]+rounds[:,6]):
                    if np.max(np.abs(rounds[:,2]-total),initial=0)>1e-8:
                        raise RuntimeError('HARD_STOP_DSE_round_time_reconciliation')
                measured=float(rounds[:,7].sum()/480/1e9)
                if not np.isclose(measured,point['metrics']['dit_GB_per_req'],rtol=1e-10,atol=1e-10):
                    raise RuntimeError('HARD_STOP_DSE_DiT_traffic_reconciliation')
        rows.append(dict(path=str(path),sha256=digest(path),raw_sha256=status['raw_sha256']))
    write_json(ROOT/'validation/dse_archive_audit.json',dict(passed=True,evaluations=len(rows),
        archived_rounds=round_count,evidence=rows,
        scope='Every repaired/supplement evaluation reopened: hashes, finite ordered timestamps, compute+memory '
            'and linear+attention round time, all-round DiT traffic/request reconciliation.'))
    print('DSE archives verified',len(rows),flush=True)


def selected():
    points=read_csv(ROOT/'paper/selected_conditional_points.csv');count=0
    for row in points:
        directory=ROOT/'paper/selected_rechecks'/row['point_id'];status=load(directory/'status.json')
        if not status['gate']['pass_gate'] or digest(directory/'requests.npz')!=status['raw_sha256']:
            raise RuntimeError('HARD_STOP_selected_reference_checkpoint')
        with np.load(directory/'requests.npz') as data:
            if data['original'].shape!=(960,4) or not np.isfinite(data['original']).all():
                raise RuntimeError('HARD_STOP_selected960_raw')
            if np.max(np.abs(data['original']-data['fast']))>1e-6:
                raise RuntimeError('HARD_STOP_selected960_identity')
        directory=ROOT/'paper/selected_stress'/row['point_id'];status=load(directory/'status.json')
        for name,sha in status['hashes'].items():
            if digest(directory/name)!=sha:raise RuntimeError('HARD_STOP_selected_stress_archive')
        with np.load(directory/'requests.npz') as data:
            raw=data['requests']
            if raw.shape!=(status['runs'],480,4) or not np.isfinite(raw).all() or (np.diff(raw,axis=2)<-1e-8).any():
                raise RuntimeError('HARD_STOP_selected_stress_raw')
            k=1 if row['mode']=='serial' else int(row['dit_stages']);stop=480-k-2
            for stress in read_csv(directory/'runs.csv'):
                r=raw[int(stress['raw_index'])]
                pair=[float(np.mean(r[96:stop,3]-r[96:stop,0])),float(np.mean(np.diff(r[95:stop,3])))]
                if not np.allclose(pair,[float(stress['L_s']),float(stress['S_s'])],rtol=0,atol=1e-8):
                    raise RuntimeError('HARD_STOP_selected_stress_LS')
                count+=1
    write_json(ROOT/'validation/selected_archive_audit.json',dict(passed=True,points=len(points),stress_runs=count,
        scope='Every selected reference/stress archive reopened, hashes/shape/finite/order and raw L/S reconciliation.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('native','band','dse','selected'));a=p.parse_args()
    {'native':native,'band':band,'dse':dse,'selected':selected}[a.stage]()
