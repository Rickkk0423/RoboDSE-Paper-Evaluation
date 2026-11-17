"""V5.1 frozen native controls, automatic W5 fallback, and audited replay."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import time

import numpy as np

from case_v3_p0 import digest
from run_native import load_backend
from v5_native import build, execute
from v51_catalog import catalog, check_accounting, export, finalize, memories
from v51_bg import transform


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


class Runner:
    def __init__(self, backend, output):
        self.backend, self.output = Path(backend).resolve(), Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        for name in ('v51_native.py','v51_catalog.py','v51_bg.py','v5_driver.cpp','v5_native.py',
                     'case_v3_p0.py','channel_frontend.py','run_native.py'):
            shutil.copy2(Path(__file__).with_name(name), self.output/name)
        self.Ramulator, _ = load_backend(self.backend)
        self.library = self.backend/'build'/('libneusim_ramulator_bridge'+
            ('.dylib' if sys.platform=='darwin' else '.so'))
        self.driver = build(self.output)
        self.identity = dict(source_manifest_sha256=digest(self.backend/'source_manifest.json'),
            bridge_sha256=digest(self.library), driver_source_sha256=digest(self.output/'v5_driver.cpp'))

    def replay(self, config, trace, label, *, bg=False, mapper='MOP4CLXOR', force_instances=False):
        out = self.output/label
        out.mkdir(exist_ok=False)
        geometry = export(config, out/'dram.yaml', mapper, force_instances=force_instances)
        with np.load(trace) as data:
            counts = [int(np.count_nonzero(data['core']==i))*64 for i in (0,1)]
        started = time.monotonic()
        write(out/'manifest.json', dict(config=config, geometry=geometry, trace_sha256=digest(trace),
            bg=bg, identity=self.identity, counts=counts))
        mapped=out/'mapped_logical64.npz' if bg else trace
        if bg:
            transform(trace,mapped,config['channels'],geometry['mop_geometry'])
        with memories(self.Ramulator, out/'dram.yaml', self.library, geometry) as devices:
            first = devices[0] if isinstance(devices,list) else devices
            width = max(8, math.ceil(geometry['peak_GBps']*first.tck_ns/32))
            native = execute(devices, mapped, channels=config['channels'], issue_width=width,
                driver=self.driver, library=self.library)
            stats = finalize(devices, out, label)
        audit = check_accounting(native, stats, counts)
        end = max(x for x in native['last_completion_ns'] if x is not None)
        result = dict(id=label, config=config, bg=bg, geometry=geometry, native=native,
            achieved_GBps=native['logical_bytes']/end, eta_peak=native['logical_bytes']/end/geometry['peak_GBps'],
            accounting=audit, trace_sha256=digest(trace), stats_sha256={p.name:digest(p) for p in stats},
            mapped_trace_sha256=digest(mapped),
            wall_seconds=time.monotonic()-started, identity=self.identity)
        write(out/'result.json', result)
        print(label, 'eta_peak', round(result['eta_peak'],9), flush=True)
        return result


def equivalence(runner):
    n = 8192
    trace = runner.output/'probe.npz'
    np.savez_compressed(trace, issue_ns=np.arange(n)//512*300.,
        core=(np.arange(n)//17%2).astype(np.uint8), address=np.arange(n,dtype=np.uint64)*64,
        write=(np.arange(n)%19==0).astype(np.uint8), owner=(np.arange(n)//17%2).astype(np.uint8))
    rows = []
    for config in [c for c in catalog() if c['id'] in ('LPDDR5_c16','HBM2_c8','GDDR6_c16')]:
        for bg in (False,True):
            label = config['id']+('_bg' if bg else '_plain')
            normal = runner.replay(config, trace, label+'_native', bg=bg)
            split = runner.replay(config, trace, label+'_instances', bg=bg, force_instances=True)
            differences = [key for key in normal['native'] if normal['native'][key] != split['native'][key]]
            if differences:
                write(runner.output/'failure.json',dict(reason='HARD_STOP_instance_equivalence',
                    id=label, differences=differences))
                raise RuntimeError('HARD_STOP_instance_equivalence '+str(differences))
            rows.append(dict(id=label,native=normal['native'],exact=True))
    for config in [c for c in catalog() if c['channels'] in (24,36)]:
        for bg in (False, True):
            row = runner.replay(config,trace,config['id']+('_bg' if bg else '_plain'),bg=bg)
            rows.append(dict(id=row['id'],native=row['native'],accounting=True))
    write(runner.output/'equivalence.json',dict(passed=True,probes=rows,identity=runner.identity,
        scope='Six exact native aggregate-vs-independent-instance controls plus '
              'four actual non-power-of-two native count/capacity controls. '
              'Modulo/division is a bijective channel demux, not capacity wrapping.'))


def selfcheck(runner, source, index):
    manifest = json.loads((source/'manifest.json').read_text())
    item = manifest['items'][index]
    config = item['config']
    write(runner.output/'frozen_input.json',dict(manifest_sha256=digest(source/'manifest.json'),item=item))
    seqs = []
    for trace in manifest['seq_traces']:
        if digest(source/trace['path']) != trace['sha256']:
            raise RuntimeError('HARD_STOP_frozen_trace_hash_mismatch')
        seqs.append(runner.replay(config, source/trace['path'], trace['id']))
    eta = float(np.median([r['eta_peak'] for r in seqs]))
    selection = 'MOP4CLXOR'
    alternatives = []
    if min(r['eta_peak'] for r in seqs) < .8:
        trial = [runner.replay(config,source/t['path'],
                 'alternate_'+t['id'],mapper='ChRaBaRoCo') for t in manifest['seq_traces']]
        alternatives = trial
        if min(r['eta_peak'] for r in trial)>min(r['eta_peak'] for r in seqs):
            seqs = trial
            eta = float(np.median([r['eta_peak'] for r in seqs]))
            selection = 'ChRaBaRoCo'
    levels = []
    chosen = None
    for trace in item['levels']:
        if digest(source/trace['path']) != trace['sha256']:
            raise RuntimeError('HARD_STOP_frozen_trace_hash_mismatch')
        try:
            row = runner.replay(config,source/trace['path'],'W5_level'+str(trace['level']),mapper=selection)
        except ValueError as error:
            if 'capacity' not in str(error):
                raise
            levels.append(dict(level=trace['level'],block_bytes=trace['block_bytes'],
                status='unverifiable_capacity',reason=str(error)))
            continue
        ratio = row['eta_peak']/eta
        levels.append(dict(level=trace['level'],block_bytes=trace['block_bytes'],
            ratio=ratio,passed=ratio>=.9,result=str(Path(row['id'])/'result.json')))
        if ratio>=.9:
            chosen = trace
            break
    hbm = None
    if config['id']=='HBM2_c8':
        old = manifest['legacy_hbm_calibration']
        difference = abs(eta/old['params']['eta_seq']-1)
        hbm = dict(legacy_eta_seq=old['params']['eta_seq'],new_eta_seq=eta,
            relative_difference=difference,identity='new_separate_calibration' if difference>.03
                else 'within_3pct_of_v3_new_capacity_identity',
            seq_three_granularities=[r['eta_peak'] for r in seqs],
            full_period_sampled_W5_completed=any('ratio' in r for r in levels))
        if chosen is not None:
            try:
                bg = runner.replay(config,source/chosen['path'],'HBM_full_period_BG',bg=True,mapper=selection)
                hbm['full_period_BG']=dict(native=bg['native'],capacity_bytes=bg['geometry']['capacity_bytes'],
                    peak_mapped_address_check='execute checked all mapped native addresses, no capacity wrapping')
            except ValueError as error:
                hbm['full_period_BG']=dict(status='capacity_failure',reason=str(error))
    status = dict(id=config['id'],config=config,geometry=seqs[0]['geometry'],mapper=selection,
        params=dict(eta_seq=eta),seq_min=min(r['eta_peak'] for r in seqs),
        seq_gate=all(r['eta_peak']>=.8 for r in seqs),
        seq=[dict(id=r['id'],eta_peak=r['eta_peak']) for r in seqs],
        alternative_mapper_runs=[dict(id=r['id'],eta_peak=r['eta_peak']) for r in alternatives],
        sampling=dict(level=chosen['level'] if chosen else 3, block_bytes=chosen['block_bytes'] if chosen else None,
            status='validated' if chosen else 'W5_unverified',levels=levels,
            trace=chosen['path'] if chosen else None,span_derivation=item['geometry']['row_spans']),
        hbm_acceptance=hbm,identity=runner.identity,
        source_manifest_sha256=digest(source/'manifest.json'))
    write(runner.output/'status.json',status)


def batch(runner,source,index):
    manifest=json.loads((source/'manifest.json').read_text())
    item=manifest['items'][index]
    write(runner.output/'frozen_input.json',dict(manifest_sha256=digest(source/'manifest.json'),item=item))
    rows=[]
    for task in item['tasks']:
        path=source/task['path']
        if digest(path)!=task['sha256']:
            raise RuntimeError('HARD_STOP_frozen_trace_hash_mismatch')
        try:
            native=runner.replay(item['config'],path,task['id'],bg=task.get('bg',False),
                mapper=item.get('mapper','MOP4CLXOR'))
            rows.append(dict(task=task,result=native))
        except ValueError as error:
            if 'capacity' not in str(error):
                raise
            rows.append(dict(task=task,status='unverifiable_capacity',reason=str(error)))
    write(runner.output/'status.json',dict(id=item['id'],rows=rows,
        source_manifest_sha256=digest(source/'manifest.json'),identity=runner.identity))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--mode',choices=('catalog','equivalence','selfcheck','batch'),required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--index',type=int)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    try:
        runner = Runner(args.backend,args.out)
        if args.mode=='catalog':
            rows = [dict(config=c,geometry=export(c,args.out/(c['id']+'.yaml'))) for c in catalog()]
            write(args.out/'catalog.json',dict(memories=rows,identity=runner.identity))
        elif args.mode=='equivalence':
            equivalence(runner)
        elif args.mode=='selfcheck':
            selfcheck(runner,args.input,args.index)
        else:
            batch(runner,args.input,args.index)
    except Exception as error:
        write(args.out/'failure.json',dict(type=type(error).__name__,message=str(error)))
        raise


if __name__=='__main__':
    main()
