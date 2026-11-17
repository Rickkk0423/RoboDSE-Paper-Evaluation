"""Repair blank-config-ID control cache aliasing without changing frozen band evidence."""
from concurrent.futures import ProcessPoolExecutor,as_completed
import itertools
import sys

import numpy as np

from v6_common import ROOT,OLD,load,write_json,write_csv,digest
from v51_package import read_csv
from v51_dse import semantic_key
from v6_band import engine_from_row
from v4_scheduler import periodic_gate


def run_shard(key):
    memory,cores=key;out=ROOT/'band/control_repair/shards'/f'{memory}_c{cores}'
    if (out/'status.json').exists():
        status=load(out/'status.json')
        for name,sha in status['hashes'].items():
            if digest(out/name)!=sha:raise RuntimeError('Control repair checkpoint hash changed')
        return status
    out.mkdir(parents=True,exist_ok=True)
    original=[r for r in read_csv(ROOT/'band/inputs.csv') if r['memory']==memory and int(r['n_cores'])==cores]
    inputs=[(i,r) for i,r in enumerate(original) if r['band_role']=='same_allocation_control']
    q=load(ROOT/'band/quantiles.json')['groups'];cal=load(OLD/'calibration.json')
    standard=cal[memory]['config']['standard'];library=ROOT/'band'/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    results=[];raw=[];evidence=[];cache={}
    for index,row in inputs:
        # A missing external config_id is never a semantic cache key.
        engine=engine_from_row(row,library,calibrations=cal);semantic=semantic_key(engine);period=float(row['period_s'])
        for window in ('W1','W3','W4','W5'):
            v=q.get('/'.join((standard,window,'vlm')));d=q.get('/'.join((standard,window,'dit')))
            if v is None and d is None:continue
            for vp,dp in itertools.product(('p5','p50','p95') if v else ('unmeasured_unchanged',),
                                          ('p5','p50','p95') if d else ('unmeasured_unchanged',)):
                scales=(1/(1+v[vp]) if v else 1.,1/(1+d[dp]) if d else 1.)
                identity=semantic,period,*scales
                if identity not in cache:
                    scaled=engine_from_row(row,library,scales,cal);result=scaled.run(period)
                    gate=periodic_gate(result,period,scaled.k)
                    raw.append(np.array([[r[k] for k in ('obs_s','vlm_start_s','vlm_end_s','done_s')] for r in result['requests']]))
                    value=dict(pass_gate=gate['pass_gate'],L_s=gate['L_mean_s'],S_s=gate['S_mean_s'],
                        raw_index=len(raw)-1,vlm_scale=scales[0],dit_scale=scales[1])
                    evidence.append(dict(semantic=semantic,period_s=period,k=scaled.k,**value));cache[identity]=value
                results.append(dict(input_index=index,hardware_id=row['hardware_id'],config_id=row['config_id'],model=row['model'],
                    track=row['track'],bw_policy=row['bw_policy'],bg=row['bg'],mode=row['mode'],dit_stages=row['dit_stages'],
                    dit_batching=row['dit_batching'],band_role=row['band_role'],window=window,vlm_quantile=vp,dit_quantile=dp,
                    period_s=period,**cache[identity]))
    if raw:np.savez_compressed(out/'requests.npz',requests=np.stack(raw))
    else:np.savez_compressed(out/'requests.npz',requests=np.zeros((0,480,4)))
    write_csv(out/'runs.csv',results);write_json(out/'evidence.json',evidence)
    status=dict(memory=memory,cores=cores,input_rows=len(inputs),rows=len(results),unique_runs=len(raw),
        source_sha256=digest(__file__),hashes={name:digest(out/name) for name in ('requests.npz','runs.csv','evidence.json')})
    write_json(out/'status.json',status);print('Corrected control band',memory,cores,len(raw),flush=True)
    return status


def run(workers=4):
    out=ROOT/'band/control_repair';out.mkdir(exist_ok=True)
    rows=read_csv(ROOT/'band/inputs.csv');keys=sorted({(r['memory'],int(r['n_cores'])) for r in rows})
    manifest=dict(input_sha256=digest(ROOT/'band/inputs.csv'),source_sha256=digest(__file__),
        scope='Replace only11200 same-allocation control rows. Initial frozen campaign retained untouched; '
            'blank config IDs aliased engine metadata/cache keys across k. All21580 original frontier inputs remain unaffected.',
        cause='v6_band.run_shard engine_cache keyed by empty config_id; fixed cache keys use full semantic identity and scaled.k gate.',
        initial_failed_audit='results/v6/execution/finish/attempt_0/05_audit_band.log')
    if (out/'manifest.json').exists() and load(out/'manifest.json')!=manifest:raise RuntimeError('Frozen corrected control source changed')
    write_json(out/'manifest.json',manifest)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(run_shard,k) for k in keys]):f.result()


if __name__=='__main__':run()
