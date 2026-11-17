"""960-request identity rechecks and empirical stresses for conditional paper pairs."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import replace
import itertools
import sys

import numpy as np

from v6_common import ROOT,load,write_json,write_csv,digest
from v51_package import read_csv
from v6_band import engine_from_row
from v4_scheduler import periodic_gate


def reference(row):
    out=ROOT/'paper/selected_rechecks'/row['point_id'];out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():
        saved=load(out/'status.json')
        if digest(out/'requests.npz')!=saved['raw_sha256']:
            raise RuntimeError('HARD_STOP_selected_reference_hash')
        return saved
    library=ROOT/'band'/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    engine=engine_from_row(row,library,calibrations=load(ROOT/'calibration.json'))
    period=float(row['T_s']);engine.reference.mp=replace(engine.reference.mp,launch_period_s=period)
    original=engine.reference.run(960,192,diagnostics=True);fast=engine.run(period,960)
    columns=('obs_s','vlm_start_s','vlm_end_s','done_s')
    a=np.array([[r[k] for k in columns] for r in original['requests']])
    b=np.array([[r[k] for k in columns] for r in fast['requests']])
    error=float(np.max(np.abs(a-b)))
    if error>1e-6:
        write_json(ROOT/'hard_stop.json',dict(reason='selected960_reference_mismatch',point_id=row['point_id'],error=error))
        raise RuntimeError('HARD_STOP_selected960_reference_difference')
    gate=periodic_gate(original,period,engine.k)
    np.savez_compressed(out/'requests.npz',original=a,fast=b)
    status=dict(point_id=row['point_id'],gate=gate,max_absolute_error_s=error,
        raw_sha256=digest(out/'requests.npz'),source_sha256=digest(__file__))
    write_json(out/'status.json',status)
    return status


def recheck(workers=2):
    points=read_csv(ROOT/'paper/selected_conditional_points.csv')
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results=[f.result() for f in as_completed([pool.submit(reference,r) for r in points])]
    write_json(ROOT/'paper/selected_recheck_status.json',dict(points=len(points),
        failed=[r['point_id'] for r in results if not r['gate']['pass_gate']],
        max_absolute_error_s=max((r['max_absolute_error_s'] for r in results),default=0),
        point_statuses=results,scope='960-request original Python scheduler and compiled identity, all four request timestamps.'))
    print('Selected960',len(results),'failed',sum(not r['gate']['pass_gate'] for r in results),flush=True)


def stress():
    points=read_csv(ROOT/'paper/selected_conditional_points.csv');q=load(ROOT/'band/quantiles.json')['groups']
    library=ROOT/'band'/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    cal=load(ROOT/'calibration.json');out=ROOT/'paper/selected_stress';out.mkdir(exist_ok=True)
    results=[]
    for row in points:
        target=out/row['point_id'];target.mkdir(exist_ok=True)
        if (target/'status.json').exists():
            status=load(target/'status.json')
            for name,sha in status['hashes'].items():
                if digest(target/name)!=sha:raise RuntimeError('HARD_STOP_selected_stress_hash')
            results.extend(read_csv(target/'runs.csv'));continue
        raw=[];rows=[];standard=row['memory'].split('_')[0]
        for window in ('W1','W3','W4','W5'):
            v=q.get('/'.join((standard,window,'vlm')));d=q.get('/'.join((standard,window,'dit')))
            if v is None and d is None:continue
            for vp,dp in itertools.product(('p5','p50','p95') if v else ('unmeasured_unchanged',),
                                          ('p5','p50','p95') if d else ('unmeasured_unchanged',)):
                scales=(1/(1+v[vp]) if v else 1.,1/(1+d[dp]) if d else 1.)
                engine=engine_from_row(row,library,scales,cal);result=engine.run(float(row['T_s']))
                gate=periodic_gate(result,float(row['T_s']),engine.k)
                raw.append(np.array([[r[k] for k in ('obs_s','vlm_start_s','vlm_end_s','done_s')] for r in result['requests']]))
                rows.append(dict(point_id=row['point_id'],memory=row['memory'],window=window,vlm_quantile=vp,dit_quantile=dp,
                    vlm_scale=scales[0],dit_scale=scales[1],L_s=gate['L_mean_s'],S_s=gate['S_mean_s'],
                    pass_gate=gate['pass_gate'],raw_index=len(raw)-1,
                    transfer_status='old_heldout_errors_transferred_UNVALIDATED_new_identity' if row['evidence_root']==str(ROOT)
                        else 'empirical_old_heldout_stress_not_CI'))
        np.savez_compressed(target/'requests.npz',requests=np.stack(raw));write_csv(target/'runs.csv',rows)
        write_json(target/'status.json',dict(point_id=row['point_id'],runs=len(rows),source_sha256=digest(__file__),
            hashes={name:digest(target/name) for name in ('requests.npz','runs.csv')}))
        results.extend(rows)
    write_csv(ROOT/'paper/selected_stress_runs.csv',results)
    lookup=defaultdict(dict)
    for r in results:
        lookup[r['point_id']][r['window'],r['vlm_quantile'],r['dit_quantile']]=r
    comparisons=read_csv(ROOT/'paper/selection_comparison_within_memory.csv')
    for row in comparisons:
        a,b=row.get('serial_point_id'),row.get('task_point_id')
        if not a or not b:continue
        joint=0;task=0;serial=0;keys=set(lookup[a])&set(lookup[b])
        for key in keys:
            x,y=lookup[a][key],lookup[b][key]
            xf=x['pass_gate'] in (True,'True') and float(x['L_s'])*1000<=float(row['Smax_ms'])+1e-9
            yf=y['pass_gate'] in (True,'True') and float(y['L_s'])*1000<=float(row['Lmax_ms'])+1e-9 and float(y['S_s'])*1000<=float(row['Smax_ms'])+1e-9
            serial+=xf;task+=yf;joint+=xf and yf
        row.update(stress_scenarios=len(keys),serial_feasible_stress_fraction=serial/len(keys),
            task_feasible_stress_fraction=task/len(keys),joint_feasible_stress_fraction=joint/len(keys),
            error_band_robust_fraction=joint/len(keys) if float(row['area_difference_value_mm2'])<=1e-12 else 0.,
            robustness_scope='Matched empirical quantile-rank scenarios at fixed nominal pair/period. NOT probability/CI; '
                'new identities transfer old residuals without validation. No per-scenario global cost reoptimization.')
    write_csv(ROOT/'paper/selection_comparison_within_memory.csv',comparisons)
    write_json(ROOT/'paper/selected_stress_status.json',dict(points=len(points),runs=len(results),
        stable_runs=sum(r['pass_gate'] in (True,'True') for r in results),
        source_sha256=digest(__file__),scope='Conditional within-tier comparisons only; global cost conclusion remains blocked.'))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('recheck','stress'));a=p.parse_args()
    recheck() if a.action=='recheck' else stress()
