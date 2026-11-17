"""Independent archive/count/hash audit and explicit cross-host evidence."""
from pathlib import Path
import sys
import argparse
import csv
from collections import defaultdict
import platform
import subprocess

import numpy as np

from v51_workflow import ROOT,load
from v5_audit import compare_values
from v5_protocol import digest,write_json

sys.path.insert(0,str(Path(__file__).parent/'ramulator_bridge'))
from v51_catalog import check_accounting


def audit():
    expected=load('results/case_v3_complete/experiment_manifest.json')['compute_snapshot_sha256']
    actual=digest('.native/compute/source_manifest.json')
    if actual!=expected:
        raise RuntimeError('HARD_STOP_pinned_compute_snapshot_identity_changed')
    import scipy
    write_json(ROOT/'execution/environment.json',dict(platform=platform.platform(),machine=platform.machine(),
        python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
        compiler=subprocess.run(['c++','--version'],capture_output=True,text=True,check=True).stdout,
        compute_snapshot_sha256=actual,V3_compute_snapshot_sha256=expected,
        periodic_compile_flags=['-O2','-ffp-contract=off','-std=c++17','-shared','-fPIC'],
        scope='Installed local toolchain and unchanged pinned compute source identity; native per-host binaries '
            'have separate source/build hashes in each replay archive.'))
    cross=[];controls=[]
    for label,left,right in [('equivalence',ROOT/'equivalence_local_v2/equivalence.json',
        ROOT/'equivalence_remote/shard_0/equivalence.json')]:
        cross+=compare_values(load(left)['probes'],load(right)['probes'])
        controls.append(dict(id=label,left_sha256=digest(left),right_sha256=digest(right)))
    for directory,labels in [('selfcheck',('seq_4KB','seq_64KB','seq_1024KB','W5_level1')),
        ('selfcheck_retry',('seq_4KB','seq_64KB','seq_1024KB','W5_level1','W5_level2','HBM_full_period_BG'))]:
        for label in labels:
            index=2 if directory=='selfcheck' else 7
            left=ROOT/f'{directory}_local/shard_{index}'/label/'result.json'
            right=ROOT/f'{directory}_remote/shard_{index}'/label/'result.json'
            cross+=compare_values(load(left)['native'],load(right)['native'])
            controls.append(dict(id=directory+'_'+label,left_sha256=digest(left),right_sha256=digest(right)))
    if cross:
        write_json(ROOT/'cross_host_failure.json',cross)
        raise RuntimeError('HARD_STOP_cross_host_numeric_difference')
    write_json(ROOT/'cross_host.json',dict(passed=True,differences=cross,controls=controls,tolerance=1e-6,
        scope='10 native equivalence probes, 4 full LPDDR controls and 6 full large-HBM controls'))
    completed=[]
    for directory in ('selfcheck_remote','selfcheck_retry_remote','development_native','heldout_native','calibration_native'):
        for path in (ROOT/directory).glob('shard_*/*/result.json'):
            row=load(path);manifest=load(path.parent/'manifest.json')
            if row['trace_sha256']!=manifest['trace_sha256']:
                raise RuntimeError('HARD_STOP_native_trace_identity_changed')
            stats=[]
            for name,sha in row['stats_sha256'].items():
                stat=path.parent/name
                if digest(stat)!=sha:
                    raise RuntimeError('HARD_STOP_native_stats_hash_mismatch')
                stats.append(stat)
            check_accounting(row['native'],stats,manifest['counts'])
            completed.append(dict(path=str(path.relative_to(ROOT)),sha256=digest(path),
                transactions=row['native']['completed'],logical_bytes=row['native']['logical_bytes']))
    inputs=[]
    for name in ('stage1_input','development_input','heldout_input','calibration_input'):
        directory=ROOT/name;manifest=load(directory/'manifest.json');verified=set()
        for item in manifest['items']:
            tasks=item.get('tasks',item.get('levels',[]))
            for task in tasks:
                if digest(directory/task['path'])!=task['sha256']:
                    raise RuntimeError('HARD_STOP_frozen_input_trace_hash_mismatch')
                verified.add(task['path'])
        inputs.append(dict(manifest=name,sha256=digest(directory/'manifest.json'),verified_traces=len(verified)))
    write_json(ROOT/'native_archive_audit.json',dict(passed=True,completed_replays=len(completed),
        completed=completed,inputs=inputs,total_transactions=sum(r['transactions'] for r in completed),
        scope='Independent post-execution replay accounting and archived-stat/input hash verification; '
            'OOM/timeout partial directories are preserved, not counted as completed replay identities.'))
    print('Verified native replay archives',len(completed),flush=True)


def audit_dse():
    if len(list((ROOT/'dse/shards').glob('*/status.json')))!=80 or load(ROOT/'dse/ablation_supplement/status.json')['input_completed_shards']!=80:
        raise RuntimeError('Complete DSE and supplemental controls before final archive audit')
    manifest=load(ROOT/'dse/manifest.json');rows=[];round_count=0
    current=digest(Path(__file__).with_name('v51_dse.py'))
    for name,sha in manifest['sources_sha256'].items():
        if digest(Path(__file__).with_name(name))!=sha:
            raise RuntimeError('HARD_STOP_DSE_executed_source_changed '+name)
    for name,key in (('calibration.json','calibration_sha256'),('heldout_gate.json','heldout_gate_sha256')):
        if digest(ROOT/name)!=manifest[key]:
            raise RuntimeError('HARD_STOP_DSE_frozen_input_changed '+name)
    paths=[*(ROOT/'dse/shards').glob('*/evaluations/*/status.json'),
           *(ROOT/'dse/ablation_supplement/evaluations').glob('*/status.json')]
    for path in paths:
        saved=load(path);raw=path.parent/'requests.npz'
        if saved['raw_sha256']!=digest(raw) or saved['source_sha256']!=current:
            raise RuntimeError('HARD_STOP_DSE_raw_or_source_hash_mismatch '+str(path))
        with np.load(raw) as data:
            requests=data['requests']
            if requests.shape[1:]!=(480,4) or not np.isfinite(requests).all():
                raise RuntimeError('HARD_STOP_DSE_request_archive_invalid')
            if len(requests)!=len(data['period_s']) or np.any(np.diff(requests,axis=2)<-1e-8):
                raise RuntimeError('HARD_STOP_DSE_request_archive_order_mismatch')
            for name in data.files:
                if name.startswith('curve_rounds_'):
                    rounds=data[name];round_count+=len(rounds)
                    if not np.isfinite(rounds).all():
                        raise RuntimeError('HARD_STOP_DSE_nonfinite_round_archive')
                    for total in (rounds[:,3]+rounds[:,4],rounds[:,5]+rounds[:,6]):
                        if np.max(np.abs(rounds[:,2]-total),initial=0)>1e-8:
                            raise RuntimeError('HARD_STOP_DSE_round_time_reconciliation')
        rows.append(dict(path=str(path.relative_to(ROOT)),raw_sha256=saved['raw_sha256']))
    allowed=defaultdict(lambda:float('inf'));bound_checks=prune_checks=0
    for path in (ROOT/'dse/shards').glob('*/hw_grid.csv'):
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if row['local_kb']!='512':
                    continue
                key=tuple(row[k] for k in ('memory','n_cores','sram_mb','model','track','bw_policy','bg'))
                if row.get('Tmin_s'):
                    bound_checks+=1
                    if float(row['lower_bound_s'])>float(row['Tmin_s'])+1e-8:
                        raise RuntimeError('Observed period violates assumed analytical lower bound')
                if row['status']=='lower_bound_pruned':
                    prune_checks+=1
                    if float(row['lower_bound_s'])<=1.2*allowed[key]-1e-12:
                        raise RuntimeError('Prune not supported by allowed batched/serial incumbent')
                elif row.get('Tmin_s') and (row['mode']=='serial' or row['dit_batching']=='True'):
                    allowed[key]=min(allowed[key],float(row['Tmin_s']))
    write_json(ROOT/'dse_archive_audit.json',dict(passed=True,evaluations=len(rows),
        archived_curve_rounds=round_count,evidence=rows,source_sha256=current,
        analytical_bound_observed_checks=bound_checks,allowed_incumbent_prune_checks=prune_checks,
        scope='Reopened every search/curve request archive, verified original hashes and finite ordered request '
            'timestamps; every saved curve round reconciles compute+exposed memory and linear+attention.'))
    print('Verified DSE archives',len(rows),'curve rounds',round_count,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dse',action='store_true')
    a=p.parse_args();audit_dse() if a.dse else audit()
