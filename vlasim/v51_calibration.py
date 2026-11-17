"""Freeze and collect native per-tier VLA/legacy layout calibration, never heldout."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares

from v51_workflow import ROOT,load,memory_states
from v5_protocol import digest,offered,write_json
from v4_replay_prepare import closed_prediction
from case_v3_main import write_csv
from vlasim import DRAMModel
from vlasim.workload import Pi05Workload


def mix_arrays(fraction,legacy=False,total=64*1024**2):
    wl=Pi05Workload();n=total//64
    count=int(n*fraction)
    owners=np.r_[np.zeros(count,dtype=np.uint8),np.ones(n-count,dtype=np.uint8)]
    indices=np.r_[np.arange(count,dtype=np.uint64),np.arange(n-count,dtype=np.uint64)]
    dit_layer=int(wl.dit_layer_params*wl.c.w_bytes)
    dit_region=dit_layer*wl.c.dit_layers
    # Match the allocator's contiguous DiT-weight region followed by VLM weights.
    address=indices*64+np.where(owners==0,2**30 if legacy else dit_region,0).astype(np.uint64)
    arrays=dict(issue_ns=np.arange(n,dtype=float),core=owners,owner=owners.copy(),
        address=address,write=np.zeros(n,dtype=np.uint8))
    return offered(arrays,'saturated')


def prepare():
    out=ROOT/'calibration_input';out.mkdir(exist_ok=False)
    traces={}
    for legacy in (False,True):
        for fraction in (.25,.5,.75):
            label=f'{"legacy" if legacy else "vla"}_{int(fraction*100)}'
            path=out/(label+'.npz');arrays=mix_arrays(fraction,legacy)
            np.savez_compressed(path,**arrays)
            traces[label]=dict(path=path.name,sha256=digest(path),fraction_vlm=fraction,
                bytes_by_stream=[int(np.count_nonzero(arrays['core']==i))*64 for i in (0,1)])
    items=[]
    for state in memory_states().values():
        tasks=[]
        for layout,bg in (('vla',False),('vla',True),('legacy',False),('legacy',True)):
            for fraction in (.25,.5,.75):
                trace=traces[f'{layout}_{int(fraction*100)}']
                tasks.append(dict(**trace,id=f'{state["id"]}_{layout}_{"bg" if bg else "plain"}_{int(fraction*100)}',
                    bg=bg,layout=layout,launch='saturated',window='calibration_mix',
                    params=state['params'],peak_GBps=state['geometry']['peak_GBps']))
        items.append(dict(id=state['id'],config=state['config'],mapper=state['mapper'],tasks=tasks))
    write_json(out/'manifest.json',dict(items=items,source_sha256=digest(__file__),
        scope='Separate development calibration: 64MiB read-only, 25/50/75 VLM share; '
              'each stream sequential within original VLA physical regions. '
              'Legacy layout remeasured per new identity, not claimed as historical V3 measurement. '
              'Seq three granularities reused with exact stage1 identities. No heldout input.'))


def collect():
    frozen=load(ROOT/'calibration_input/manifest.json');states=memory_states();table=[];calibrations={}
    for index,item in enumerate(frozen['items']):
        path=ROOT/f'calibration_native/shard_{index}/status.json';status=load(path)
        if status['source_manifest_sha256']!=digest(ROOT/'calibration_input/manifest.json'):
            raise RuntimeError('HARD_STOP_calibration_frozen_input_changed')
        state=states[item['id']];eta_seq=state['params']['eta_seq'];groups={}
        for row in status['rows']:
            if 'result' not in row:
                raise RuntimeError('Native calibration incomplete '+str(row))
            task=row['task'];key=task['layout']+('_bg' if task['bg'] else '_plain')
            groups.setdefault(key,[]).append(row)
        parameters={}
        for key,rows in groups.items():
            def errors(x):
                dram=DRAMModel(eta_seq=eta_seq,eta_mix=float(np.exp(x[0])))
                result=[]
                for row in rows:
                    predicted=closed_prediction(row['task']['bytes_by_stream'],row['task']['peak_GBps']*1e9,dram)
                    result.extend(a/b-1 for a,b in zip(row['result']['native']['last_completion_ns'],predicted))
                return result
            fit=least_squares(errors,[np.log(.9)],bounds=([np.log(.05)],[np.log(2.)]))
            parameters[key]=dict(eta_seq=eta_seq,eta_mix=float(np.exp(fit.x[0])),prio_leak=0.)
            for row in rows:
                task=row['task'];predicted=closed_prediction(task['bytes_by_stream'],task['peak_GBps']*1e9,
                    DRAMModel(**parameters[key]))
                for c,(a,b) in enumerate(zip(row['result']['native']['last_completion_ns'],predicted)):
                    table.append(dict(memory=item['id'],layout=key,fraction_vlm=task['fraction_vlm'],
                        stream=('vlm','dit')[c],eta_seq=eta_seq,eta_mix=parameters[key]['eta_mix'],
                        measured_ns=a,predicted_ns=b,error_pct=abs(a/b-1)*100,
                        throughput_GBps=row['result']['achieved_GBps']))
        old_cases=load('results/v4/p0a_input/manifest.json')['cases']
        literal=[c for c in old_cases if all(c['calibration']['backend_metadata']['config'].get(k)==item['config'].get(k)
            for k in ('standard','channels','organization','timing'))]
        baseline={}
        for bg in (False,True):
            exact=next((c for c in literal if c['config']['bg']==bg),None)
            legacy_key='legacy_bg' if bg else 'legacy_plain'
            balanced=next(r for r in groups[legacy_key] if r['task']['fraction_vlm']==.5)
            old_form=dict(eta_seq=eta_seq,eta_mix=balanced['result']['achieved_GBps']/
                state['geometry']['peak_GBps']/eta_seq,prio_leak=0.)
            baseline['bg' if bg else 'plain']=dict(
                params=exact['calibration']['params'] if exact else old_form,
                scope='literal_V3_matching_native_identity' if exact else 'V3_model_form_remeasured_new_identity',
                fit_method='historical_V3_frozen' if exact else 'balanced_native_total_throughput_divided_by_seq_BW',
                balanced_native_id=balanced['task']['id'])
        result=dict(id=item['id'],version='V5.1-native-tier-layout-constant',params=parameters,baseline=baseline,
            config=item['config'],geometry=state['geometry'],mapper=state['mapper'],sampling=state['sampling'],
            seq=state['seq'],seq_gate=state['seq_gate'],alternative_mapper_runs=state['alternative_mapper_runs'],
            source_manifest_sha256=digest(ROOT/'calibration_input/manifest.json'),
            collector_source_sha256=digest(__file__),
            native_status_sha256=digest(path),hbm_acceptance=state['hbm_acceptance'],
            legacy_scope='V3 model form remeasured for this identity, not literal transfer/interpolation',
            physical_limitations='GDDR6 NoRefresh matches pinned backend smoke configuration; physical refresh unvalidated'
                if item['config']['standard']=='GDDR6' else None)
        write_json(ROOT/'calib'/f'dram_v51_{item["id"]}.json',result);calibrations[item['id']]=result
    write_json(ROOT/'calibration.json',calibrations);write_csv(ROOT/'calibration_metrics.csv',table)
    gates=load(ROOT/'gates.json');gates['stage3']=dict(status='completed_native_all_10_tiers',
        tiers=len(calibrations),mix_traces=len(table)//2,seq_runs=30,heldout_used_for_fit=False)
    write_json(ROOT/'gates.json',gates)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','collect'))
    a=p.parse_args();{'prepare':prepare,'collect':collect}[a.action]()
