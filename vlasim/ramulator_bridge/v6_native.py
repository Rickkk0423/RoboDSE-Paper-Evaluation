"""Audited V6 native mapper/refresh/frontend controls, unchanged pinned backend."""
import argparse
import copy
import math
from pathlib import Path
import sys
import time

import numpy as np
import yaml

from v51_native import Runner,write
from v51_catalog import export,memories,finalize,check_accounting
from v51_bg import transform
from v5_native import execute
from case_v3_p0 import digest


def geometry(config,path,mapper,mode):
    base='MOP4CLXOR' if mapper=='RITAddrMapper' else mapper
    geo=export(config,path,base,force_instances=mode=='independent')
    expanded=geo['expanded']
    if mode=='aggregate' and geo['instances']>1:
        expanded['controllers']=[copy.deepcopy(expanded['controllers'][0]) for _ in range(config['channels'])]
        geo['instances']=1;geo['instance_capacity_bytes']=geo['capacity_bytes']
    if mapper=='RITAddrMapper':
        for controller in expanded['controllers']:
            controller['addr_mapper']=dict(impl='RITAddrMapper',reserved_rows_per_bank=0,
                addr_mapper=dict(impl='MOP4CLXOR'))
    path.write_text(yaml.safe_dump(dict(frontend=dict(impl='NeuSimExternal',num_cores=2,
        address_capacity_bytes=geo['instance_capacity_bytes']),memory_system=expanded),sort_keys=False))
    geo.update(mapper=mapper,mode=mode,yaml_sha256=digest(path))
    return geo


def replay(runner,item,task,source):
    out=runner.output/task['id'];out.mkdir(exist_ok=False)
    trace=source/task['path']
    if digest(trace)!=task['sha256']:
        raise RuntimeError('HARD_STOP_frozen_trace_hash')
    geo=geometry(item['config'],out/'dram.yaml',item['mapper'],item['mode'])
    mapped=out/'mapped_logical64.npz' if task.get('bg') else trace
    if task.get('bg'):
        if item['mapper'] not in ('MOP4CLXOR','RITAddrMapper'):
            raise ValueError('BG inversion only verified for MOP4CLXOR')
        transform(trace,mapped,item['config']['channels'],geo['mop_geometry'])
    with np.load(trace) as data:
        counts=[int(np.count_nonzero(data['core']==i))*64 for i in (0,1)]
    write(out/'manifest.json',dict(item=item,task=task,geometry=geo,counts=counts,
        trace_sha256=digest(trace),identity=runner.identity))
    started=time.monotonic()
    with memories(runner.Ramulator,out/'dram.yaml',runner.library,geo) as devices:
        first=devices[0] if isinstance(devices,list) else devices
        width=max(8,math.ceil(geo['peak_GBps']*first.tck_ns/32))
        native=execute(devices,mapped,channels=item['config']['channels'],issue_width=width,
            outstanding=item['outstanding'],driver=runner.driver,library=runner.library)
        stats=finalize(devices,out,task['id'])
    audit=check_accounting(native,stats,counts)
    end=max(x for x in native['last_completion_ns'] if x is not None)
    result=dict(native=native,geometry=geo,accounting=audit,eta_peak=native['logical_bytes']/end/geo['peak_GBps'],
        achieved_GBps=native['logical_bytes']/end,identity=runner.identity,trace_sha256=digest(trace),
        mapped_trace_sha256=digest(mapped),stats_sha256={p.name:digest(p) for p in stats},wall_seconds=time.monotonic()-started)
    write(out/'result.json',result)
    print(task['id'],result['eta_peak'],flush=True)
    return result


def run(source,index,output,backend):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    item=__import__('json').loads((source/'manifest.json').read_text())['items'][index]
    runner=Runner(backend,output);rows=[]
    try:
        # The pinned channel mapper explicitly rejects non-power-of-two aggregates.
        # Still instantiate one to archive its actual constructor exception.
        for task in item['tasks']:
            try:
                result=replay(runner,item,task,source)
                rows.append(dict(task=task,result=result))
            except Exception as error:
                if 'power-of-two channel count' not in str(error):
                    raise
                rows.append(dict(task=task,status='unsupported_pinned_backend',reason=str(error)))
                break
        write(output/'status.json',dict(item=item,rows=rows,source_manifest_sha256=digest(source/'manifest.json'),
            source_sha256=digest(Path(__file__)),identity=runner.identity))
    except Exception as error:
        write(output/'failure.json',dict(type=type(error).__name__,message=str(error)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','backend'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--index',type=int,required=True)
    a=p.parse_args();run(a.source,a.index,a.output,a.backend)
