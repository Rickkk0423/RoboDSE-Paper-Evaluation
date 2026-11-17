"""Empirical signed-error stress bands on frozen frontier points and same-HW controls."""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import ctypes as ct
from dataclasses import fields
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

from v6_common import ROOT,OLD,load,write_json,write_csv,digest
from v51_package import read_csv
from v51_fast import Periodic
from v51_dse import semantic_key
from v4_scheduler import periodic_gate
from vlasim import HWConfig,MapConfig,DRAMModel
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def build():
    out=ROOT/'band';out.mkdir(parents=True,exist_ok=True)
    path=out/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    subprocess.run(['c++','-O2','-ffp-contract=off','-std=c++17','-shared','-fPIC',
        str(Path(__file__).with_name('v6_periodic.cpp')),'-o',str(path)],check=True)
    return path


class ScaledPeriodic(Periodic):
    def __init__(self,*args,scales=(1.,1.),**kwargs):
        if any(not np.isfinite(s) or s<=0 for s in scales):
            raise ValueError('Positive finite bandwidth multipliers required')
        super().__init__(*args,**kwargs)
        function=self.lib.periodic_run
        function.argtypes=function.argtypes[:8]+[ct.c_double,ct.c_double]+function.argtypes[8:]
        self.scales=scales
        self.lib=SimpleNamespace(periodic_run=lambda *a:function(*a[:8],*scales,*a[8:]),
            periodic_error=self.lib.periodic_error)


def quantiles():
    groups=defaultdict(list)
    for row in read_csv(OLD/'heldout_metrics.csv'):
        if row['launch']=='saturated':
            groups[row['standard'],row['window'],row['stream']].append(float(row['signed_error_pct'])/100)
    rows=[];out={}
    for key,values in sorted(groups.items()):
        q=np.quantile(values,[.05,.5,.95])
        row=dict(standard=key[0],window=key[1],stream=key[2],n=len(values),
            **{p:float(v) for p,v in zip(('p5','p50','p95'),q)})
        rows.append(row);out['/'.join(key)]=row
    write_csv(ROOT/'band/quantiles.csv',rows)
    write_json(ROOT/'band/quantiles.json',dict(groups=out,source_sha256=digest(OLD/'heldout_metrics.csv'),
        error_definition='e = native_duration / predicted_duration - 1; bandwidth factor = 1/(1+e).',
        scope='Empirical saturated-flow quantiles pooled across plain/BG within standard/window/stream. '
            'Sparse samples, not confidence or simultaneous coverage bounds. No heldout refitting. '
            'Apply each window-specific pair globally as a stress scenario, not an operation-phase error model. '
            'W1 has no DiT samples: DiT held unchanged and explicitly unmeasured. Aggregate bandwidth capped at physical peak.'))
    return out


def parse(row,cls):
    out={}
    for f in fields(cls):
        value=row.get(f.name)
        if value in (None,'','None'):
            continue
        if value in ('True','False'):
            value=value=='True'
        elif f.name not in ('mode','vlm_launch','bw_policy'):
            try:
                value=float(value)
                if f.name in ('n_cores','array_rows','array_cols','local_kb','vlm_cores','dit_stages','vlm_queue_max','jit_freeze_after'):
                    value=int(value)
            except (ValueError,TypeError):
                pass
        out[f.name]=value
    return cls(**out)


def engine_from_row(row,library,scales=(1.,1.),calibrations=None):
    cal=(calibrations or load(OLD/'calibration.json'))[row['memory']]
    hw=parse(row,HWConfig)
    hw.dram_bw=cal['geometry']['peak_GBps']*1e9
    hw.slice_mode=row.get('track')=='analytical_sliced'
    mp=parse(row,MapConfig);mp.vlm_launch='periodic';mp.launch_period_s=1.
    bg=row['bg'] in (True,'True')
    params=cal['baseline']['bg' if bg else 'plain']['params'] if row['model']=='v3_form' else cal['params']['vla_bg' if bg else 'vla_plain']
    wl=Pi05Workload();provider=NeuSimTiming('.native/compute',wl,allow_analytical_siglip=True) if row.get('track','neusim_unsliced')=='neusim_unsliced' else None
    return ScaledPeriodic(hw,mp,wl,DRAMModel(**params),provider,library,scales=scales)


def prepare():
    directory=ROOT/'band';directory.mkdir(parents=True,exist_ok=True);build();q=quantiles()
    rows=[]
    for row in read_csv(OLD/'attainable.csv'):
        rows.append(dict(row,band_role='frozen_frontier',period_s=row['T_s']))
    for row in read_csv(OLD/'k_ablation.csv'):
        if row.get('Tmin_s'):
            rows.append(dict(row,track='neusim_unsliced',bw_policy='fair',band_role='same_allocation_control',period_s=row['Tmin_s']))
    for row in read_csv(OLD/'hw_grid.csv'):
        if row['mode']=='serial' and row.get('Tmin_s'):
            rows.append(dict(row,band_role='same_hardware_serial_control',period_s=row['Tmin_s']))
    write_csv(directory/'inputs.csv',rows)
    write_json(directory/'manifest.json',dict(rows=len(rows),input_sha256=digest(directory/'inputs.csv'),
        quantiles_sha256=digest(directory/'quantiles.json'),sources_sha256={p.name:digest(p)
            for p in (Path(__file__),Path(__file__).with_name('v6_periodic.cpp'))},
        reference_requests=480,warmup=96,fixed_period=True,
        scope='All V5.1 frontiers including sensitivity/scenario/baseline contexts, all saved same-split '
            'batched/unbatched controls, and serial Tmin controls. Fixed original periods, unstable cases '
            'explicitly rejected rather than reported as steady finite upper bounds.'))
    print('Band inputs',len(rows),'quantile groups',len(q),flush=True)


def run_shard(key):
    memory,cores=key;out=ROOT/'band/shards'/f'{memory}_c{cores}'
    if (out/'status.json').exists():
        saved=load(out/'status.json')
        for name,sha in saved['hashes'].items():
            if digest(out/name)!=sha:
                raise RuntimeError('HARD_STOP_band_checkpoint_hash')
        return saved
    out.mkdir(parents=True,exist_ok=True)
    inputs=[r for r in read_csv(ROOT/'band/inputs.csv') if r['memory']==memory and int(r['n_cores'])==cores]
    q=load(ROOT/'band/quantiles.json')['groups'];cal=load(OLD/'calibration.json')
    standard=cal[memory]['config']['standard'];library=ROOT/'band'/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    results=[];raw=[];evidence=[];cache={};engine_cache={}
    for number,row in enumerate(inputs):
        config=row['config_id']
        if config not in engine_cache:
            engine_cache[config]=engine_from_row(row,library,calibrations=cal)
        engine=engine_cache[config];semantic=semantic_key(engine);period=float(row['period_s'])
        for window in ('W1','W3','W4','W5'):
            v=q.get('/'.join((standard,window,'vlm')));d=q.get('/'.join((standard,window,'dit')))
            if v is None and d is None:
                continue
            vp=('p5','p50','p95') if v else ('unmeasured_unchanged',)
            dp=('p5','p50','p95') if d else ('unmeasured_unchanged',)
            for vq,dq in itertools.product(vp,dp):
                scales=(1/(1+v[vq]) if v else 1.,1/(1+d[dq]) if d else 1.)
                identity=(semantic,period,*scales)
                if identity not in cache:
                    scaled=engine_from_row(row,library,scales,cal)
                    result=scaled.run(period);gate=periodic_gate(result,period,scaled.k)
                    request=np.array([[r[k] for k in ('obs_s','vlm_start_s','vlm_end_s','done_s')] for r in result['requests']])
                    index=len(raw);raw.append(request)
                    value=dict(pass_gate=gate['pass_gate'],L_s=gate['L_mean_s'],S_s=gate['S_mean_s'],raw_index=index,
                        vlm_scale=scales[0],dit_scale=scales[1])
                    evidence.append(dict(semantic=semantic,period_s=period,**value));cache[identity]=value
                results.append(dict(input_index=number,hardware_id=row['hardware_id'],config_id=config,model=row['model'],
                    track=row.get('track'),bw_policy=row.get('bw_policy'),bg=row['bg'],mode=row['mode'],dit_stages=row['dit_stages'],
                    dit_batching=row['dit_batching'],band_role=row['band_role'],window=window,vlm_quantile=vq,dit_quantile=dq,
                    period_s=period,**cache[identity]))
    np.savez_compressed(out/'requests.npz',requests=np.stack(raw))
    write_csv(out/'runs.csv',results);write_json(out/'evidence.json',evidence)
    status=dict(memory=memory,cores=cores,input_rows=len(inputs),rows=len(results),unique_runs=len(raw),
        hashes={name:digest(out/name) for name in ('requests.npz','runs.csv','evidence.json')})
    write_json(out/'status.json',status)
    print('Band completed',memory,cores,'runs',len(raw),flush=True)
    return status


def run(workers):
    rows=read_csv(ROOT/'band/inputs.csv');keys=sorted({(r['memory'],int(r['n_cores'])) for r in rows})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run_shard,key) for key in keys]):
            future.result()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    prepare() if a.action=='prepare' else run(a.workers)
