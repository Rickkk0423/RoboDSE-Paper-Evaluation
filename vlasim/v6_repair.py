"""Select transparent seq identities and remeasure their entire layout calibration."""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import shutil

import numpy as np
from scipy.optimize import least_squares

from v6_common import ROOT,OLD,load,write_json,write_csv,digest
from v51_package import read_csv,frontier
from v4_replay_prepare import closed_prediction
from vlasim import DRAMModel


def select():
    manifest=load(ROOT/'seq_input/manifest.json');groups=defaultdict(list);rows=[]
    for index,item in enumerate(manifest['items']):
        path=ROOT/f'seq_native/shard_{index}/status.json';status=load(path)
        if status['source_manifest_sha256']!=digest(ROOT/'seq_input/manifest.json'):
            raise RuntimeError('HARD_STOP_seq_input_changed')
        etas=[r['result']['eta_peak'] for r in status['rows'] if 'result' in r]
        for row in status['rows']:
            rows.append(dict(memory=item['config']['id'],variant=item['id'],mapper=item['mapper'],
                refresh=item['config']['refresh'],mode=item['mode'],outstanding=item['outstanding'],
                grain=row['task']['path'],eta_seq=row.get('result',{}).get('eta_peak'),
                status='completed' if 'result' in row else row['status'],reason=row.get('reason','')))
        if len(etas)==3:
            groups[item['config']['id']].append(dict(item=item,index=index,eta_seq=float(np.median(etas)),
                min_seq=min(etas),seq_three_grains=etas,strict_all_grains_pass=min(etas)>=.8,
                native_status_sha256=digest(path)))
    selected={}
    for memory,variants in groups.items():
        best=max(variants,key=lambda v:(v['eta_seq'],v['item']['mode']=='aggregate',v['item']['mapper']=='MOP4CLXOR'))
        best['status']='accepted_seq_median' if best['eta_seq']>=.8 else 'excluded_low_seq'
        selected[memory]=best
    write_csv(ROOT/'seq_comparison.csv',rows)
    write_json(ROOT/'repair_selection.json',dict(tiers=selected,
        eta_definition='Median of the same three seq granularities as frozen V5.1 eta_seq. V6 >=0.80 gate uses '
            'this coefficient; each grain and stricter all-grain gate are separately reported, never hidden.',
        physical_limitations='NoRefresh acceptance remains conditional on no physical refresh; not a validated '
            'real GDDR6 device. Extra q8192 is a changed frontend identity, not a backend patch.',
        instance_scope='V5.1 HBM2_c32 was already one aggregate 32-channel handle; comparing independent handles '
            'tests the specification hypothesis rather than accepting it as a fact. Nonpower aggregates unsupported.'))
    print({m:(v['status'],v['eta_seq'],v['item']['id']) for m,v in selected.items()},flush=True)


def prepare_calibration():
    selection=load(ROOT/'repair_selection.json')['tiers'];out=ROOT/'repair_input';out.mkdir(exist_ok=False)
    old=load(OLD/'calibration_input/manifest.json');stage1=load(OLD/'stage1_input/manifest.json')
    items=[]
    for memory,value in selection.items():
        if value['status']=='excluded_low_seq':
            continue
        item=dict(value['item']);old_item=next(i for i in old['items'] if i['id']==memory)
        tasks=[]
        for task in old_item['tasks']:
            source=OLD/'calibration_input'/task['path'];target=out/task['path']
            if not target.exists():shutil.copy2(source,target)
            tasks.append(dict(task))
        entry=next(i for i in stage1['items'] if i['config']['id']==memory)
        for level in entry['levels']:
            shutil.copy2(OLD/'stage1_input'/level['path'],out/level['path'])
            tasks.append(dict(level,id='W5_level'+str(level['level']),window='W5_sampling_control',bg=False))
        item.update(id=memory,tasks=tasks,selection=value)
        items.append(item)
    write_json(out/'manifest.json',dict(items=items,selection_sha256=digest(ROOT/'repair_selection.json'),
        source_sha256=digest(__file__),scope='12 original 64MiB VLA/legacy plain/BG 25/50/75 traces per changed '
            'identity plus W5 L1/L2 controls. Same frozen development calibration traces, no heldout data.'))


def collect():
    frozen=load(ROOT/'repair_input/manifest.json');cal=load(OLD/'calibration.json');metrics=[]
    for index,item in enumerate(frozen['items']):
        status=load(ROOT/f'repair_native/shard_{index}/status.json');selected=item['selection'];memory=item['id']
        if status['source_manifest_sha256']!=digest(ROOT/'repair_input/manifest.json'):
            raise RuntimeError('HARD_STOP_repair_input_changed')
        groups=defaultdict(list);sampling=[]
        for row in status['rows']:
            if 'result' not in row:
                raise RuntimeError('Incomplete repair calibration '+str(row))
            task=row['task']
            if task.get('window')=='W5_sampling_control':
                ratio=row['result']['eta_peak']/selected['eta_seq']
                sampling.append(dict(level=task['level'],block_bytes=task['block_bytes'],ratio=ratio,passed=ratio>=.9))
            else:
                groups[task['layout']+('_bg' if task['bg'] else '_plain')].append(row)
        params={};eta_seq=selected['eta_seq'];peak=cal[memory]['geometry']['peak_GBps']*1e9
        for key,rows in groups.items():
            def residual(x):
                estimates=[]
                for row in rows:
                    p=closed_prediction(row['task']['bytes_by_stream'],peak,DRAMModel(eta_seq=eta_seq,eta_mix=float(np.exp(x[0]))))
                    estimates.extend(a/b-1 for a,b in zip(row['result']['native']['last_completion_ns'],p))
                return estimates
            fit=least_squares(residual,[np.log(.9)],bounds=([np.log(.05)],[np.log(2.)]))
            params[key]=dict(eta_seq=eta_seq,eta_mix=float(np.exp(fit.x[0])),prio_leak=0.)
            for row in rows:
                p=closed_prediction(row['task']['bytes_by_stream'],peak,DRAMModel(**params[key]))
                for stream,(a,b) in enumerate(zip(row['result']['native']['last_completion_ns'],p)):
                    metrics.append(dict(memory=memory,layout=key,fraction_vlm=row['task']['fraction_vlm'],
                        stream=('vlm','dit')[stream],actual_ns=a,predicted_ns=b,error_pct=abs(a/b-1)*100))
        baseline={}
        for bg in (False,True):
            balanced=next(r for r in groups['legacy_bg' if bg else 'legacy_plain'] if r['task']['fraction_vlm']==.5)
            baseline['bg' if bg else 'plain']=dict(params=dict(eta_seq=eta_seq,
                eta_mix=balanced['result']['achieved_GBps']/(peak/1e9)/eta_seq,prio_leak=0.),
                scope='V3_model_form_remeasured_V6_new_frontend_identity')
        adopted=next((s for s in sampling if s['passed']),None)
        cal[memory]=dict(cal[memory],version='V6-native-repaired-identity',params=params,baseline=baseline,
            config=item['config'],mapper=item['mapper'],native_mode=item['mode'],outstanding=item['outstanding'],
            geometry=status['rows'][0]['result']['geometry'],
            seq_gate=selected['strict_all_grains_pass'],seq_median_gate=True,seq_three_grains=selected['seq_three_grains'],
            sampling=dict(status='validated' if adopted else 'W5_unverified',level=adopted['level'] if adopted else 3,
                block_bytes=adopted['block_bytes'] if adopted else None,levels=sampling),
            source_manifest_sha256=digest(ROOT/'repair_input/manifest.json'),native_status_sha256=digest(ROOT/f'repair_native/shard_{index}/status.json'),
            independent_heldout_status='NOT_VALIDATED_new_identity; V5.1 residuals only transferred stress scenarios')
        write_json(ROOT/'calib'/f'dram_v6_{memory}.json',cal[memory])
    write_json(ROOT/'calibration.json',cal);write_csv(ROOT/'repair_calibration_metrics.csv',metrics)
    oldgate=load(OLD/'heldout_gate.json')
    write_json(ROOT/'heldout_gate.json',dict(oldgate,dram_model_mode='dual_model_DRAM_unvalidated_V6_identity_no_new_heldout',bg_main=False))
    print('Recalibrated',len(frozen['items']),'tiers',flush=True)


def shard(task):
    import v51_dse
    v51_dse.ROOT=ROOT
    return v51_dse.run_shard(task)


def dse(workers):
    import v51_fast
    validation=load(OLD/'fast_validation/local/status.json')
    if not validation['passed'] or not load(OLD/'fast_validation/cross_host.json')['passed']:
        raise RuntimeError('HARD_STOP_inherited_kernel_validation')
    if validation['source_sha256']!=digest('vlasim/v51_periodic.cpp') or validation['wrapper_sha256']!=digest('vlasim/v51_fast.py'):
        raise RuntimeError('HARD_STOP_validated_kernel_source_changed')
    out=ROOT/'dse';out.mkdir(exist_ok=True);v51_fast.build(out)
    selection=load(ROOT/'repair_selection.json')['tiers']
    memories=[m for m,v in selection.items() if v['status']!='excluded_low_seq']
    tasks=[(m,c,str(out),'.native/compute') for m in memories for c in (1,2,3,4,6,8,12,16)]
    manifest=dict(memories=memories,expected_shards=len(tasks),cores=[1,2,3,4,6,8,12,16],
        calibration_sha256=digest(ROOT/'calibration.json'),heldout_gate_sha256=digest(ROOT/'heldout_gate.json'),
        sources_sha256={str(p):digest(p) for p in (Path(__file__),Path('vlasim/v51_dse.py'),
            Path('vlasim/v51_fast.py'),Path('vlasim/v51_periodic.cpp'))},
        scope='Reuse unchanged V5.1 search, full mapping/hardware/model/scenario space; only repaired memory tiers.')
    if (out/'manifest.json').exists() and load(out/'manifest.json')!=manifest:
        raise RuntimeError('Frozen V6 DSE manifest changed')
    write_json(out/'manifest.json',manifest)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(shard,t) for t in tasks]):
            try:
                future.result()
            except Exception:
                for process in pool._processes.values():
                    process.terminate()
                raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('select','prepare','collect','dse'))
    p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    {'select':select,'prepare':prepare_calibration,'collect':collect,'dse':lambda:dse(a.workers)}[a.action]()
