"""No-incumbent-pruning primary-case search; never modifies frozen V7."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vlasim'))
from v7_common import read_csv, write_csv, write_json, BOXES, feasible, pareto
from v6_band import engine_from_row
from v51_dse import evaluate, semantic_key, summarize
from v7_validate import accounting

OUT=ROOT/'results/v8_no_batching_case'


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    lib=OUT/'periodic.dylib'
    if not lib.exists():
        subprocess.run(['c++','-O2','-ffp-contract=off','-std=c++17','-shared','-fPIC',
                        'vlasim/v6_periodic.cpp','-o',str(lib)],check=True)
    source=ROOT/'results/v7/inputs/candidate_points.csv'
    calibration=ROOT/'results/v7/inputs/calibration.json'
    rows=read_csv(source)
    base={r['hardware_id']:r for r in rows if r['memory']=='LPDDR5_c8' and int(r['n_cores'])==4}
    identity=dict(script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source=hashlib.sha256(source.read_bytes()).hexdigest(),
        calibration=hashlib.sha256(calibration.read_bytes()).hexdigest(),
        engine_sources={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in
            ['vlasim/v6_periodic.cpp','vlasim/v51_dse.py','vlasim/v6_band.py']})
    manifest=OUT/'input_manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())!=identity:
        raise RuntimeError('Input changed; use a fresh output directory')
    write_json(manifest,identity)
    cal=json.loads(calibration.read_text())
    results=[];configs=[];cache={};checks={};failed=[]
    for hardware,template in sorted(base.items()):
        mappings=[('serial',4,1,True)]+[('pipelined',split,k,batch)
            for split in range(1,4) for k,batch in [(1,True),(2,True),(3,True),(2,False),(3,False)]]
        for mode,split,k,batch in mappings:
            row=dict(template,mode=mode,vlm_cores=str(split),dit_stages=str(k),dit_batching=str(batch),
                     config_id=f'case_{hardware}_{mode}_{split}_{k}_{batch}',
                     candidate_source='unpruned_primary_case_search')
            engine=engine_from_row(row,lib,calibrations=cal)
            if not engine.reference.sram_ok:
                configs.append(dict(hardware_id=hardware,mode=mode,vlm_cores=split,k=k,batching=batch,status='static_infeasible'))
                continue
            key=semantic_key(engine)
            if key not in cache:
                value=evaluate(engine,OUT/'runs'/key)
                cache[key]=value
                print('Evaluated',len(cache),mode,split,k,batch,'Tmin',value['search']['Tmin_s'],flush=True)
            value=cache[key]
            configs.append(dict(hardware_id=hardware,mode=mode,vlm_cores=split,k=k,batching=batch,
                                status=value['search']['status'],semantic_id=key))
            for point in value['curve']:
                if not point['gate']['pass_gate']:continue
                ck=(key,point['factor'])
                if ck not in checks:
                    result=engine.run(point['T_s'],960,192)
                    check=summarize(result,point['T_s'],engine.k)
                    check['accounting']=accounting(result,engine)
                    raw=OUT/'runs'/key/f'check960_{point["factor"]}.npz'
                    np.savez_compressed(raw,requests=np.array([[r[n] for n in ('obs_s','vlm_start_s','vlm_end_s','done_s')] for r in result['requests']]))
                    check['raw_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
                    write_json(raw.with_suffix('.json'),check)
                    checks[ck]=check
                check=checks[ck]
                errors=[abs(check['gate'][name]-point['gate'][name])/max(abs(point['gate'][name]),1e-30)
                        for name in ('L_mean_s','S_mean_s')]
                if not check['gate']['pass_gate'] or max(errors)>.01:
                    failed.append(dict(hardware=hardware,semantic=key,factor=point['factor'],errors=errors))
                    continue
                results.append(dict(row,**point['metrics'],T_s=point['T_s'],factor=point['factor'],
                    L_s=check['gate']['L_mean_s'],S_s=check['gate']['S_mean_s'],
                    point_id=f'case_{len(results):05d}',curve_gate=True,semantic_id=key,
                    source_template_point_id=template['point_id'],
                    raw=str(OUT/'runs'/key/'requests.npz'),raw_sha256=value['raw_sha256'],
                    recheck_raw=str(OUT/'runs'/key/f'check960_{point["factor"]}.npz'),
                    recheck_raw_sha256=check['raw_sha256'],Tmin_s=value['search']['Tmin_s'],
                    timing_scope='480-request search; 960-request retained-point consistency'))
    write_csv(OUT/'configurations.csv',configs);write_csv(OUT/'candidate_points.csv',results)
    from ablate_no_batching import allowed
    boxrows=[]
    for l,s in BOXES:
        for arm in ('serial','no_batching','full'):
            pool=[r for r in results if allowed(r,arm) and feasible(r,l,s,'latency_only' if arm=='serial' else 'task_aware')]
            best=min(pool,key=lambda r:(float(r['S_s']),float(r['L_s']))) if pool else None
            boxrows.append(dict(Lmax_ms=l,Smax_ms=s,arm=arm,feasible_points=len(pool),
                representative=best['point_id'] if best else '',
                L_ms=float(best['L_s'])*1000 if best else None,S_ms=float(best['S_s'])*1000 if best else None))
    write_csv(OUT/'box_feasibility.csv',boxrows)
    report=dict(hardware_identities=len(base),configurations=len(configs),unique_simulated_semantics=len(cache),
        checks960=len(checks),retained_points=len(results),incumbent_pruning=False,
        static_infeasible=sum(r['status']=='static_infeasible' for r in configs),
        failed_960_checks=failed,
        box200_100=[r for r in boxrows if (r['Lmax_ms'],r['Smax_ms'])==(200,100)],
        scope='LPDDR5_c8 / 102.4 GB/s / four cores; all retained SRAM variants, all three splits, k=1/2/3; not full-domain global search',
        task_episodes=0,independent_physical_validation=False)
    write_json(OUT/'summary.json',report);print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=OUT)
    OUT=parser.parse_args().out.resolve()
    run()
