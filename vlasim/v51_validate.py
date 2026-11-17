"""Long-sequence reference audit for the periodic template execution kernel."""
import argparse
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np

from v51_fast import Periodic, build
from v5_protocol import digest, write_json
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def validate(out, snapshot):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    library=build(out)
    wl=Pi05Workload();provider=NeuSimTiming(snapshot,wl,allow_analytical_siglip=True)
    records=[]
    for index,(k,period,n,policy,sram,batching) in enumerate([
        (0,.2,480,'fair',8,True),(1,.1,960,'fair',64,True),
        (2,.2,480,'fair',32,True),(3,.2,960,'fair',16,True),
        (2,.5,960,'vlm_priority',64,True),(3,.1,480,'fair',8,False)]):
        hw=HWConfig(n_cores=6,sram_mb=sram,dram_bw=256e9,slice_mode=False,dram_priority=False)
        mp=MapConfig(mode='serial' if not k else 'pipelined',vlm_cores=3,
            dit_stages=max(k,1),bw_policy=policy,dit_batching=batching,
            vlm_launch='periodic',launch_period_s=period)
        dram=DRAMModel(eta_seq=.915,eta_mix=.85)
        a=Simulator(hw,mp,wl,dram,provider).run(n,n//5,diagnostics=True)
        b=Periodic(hw,mp,wl,dram,provider,library).run(period,n)
        errors=[]
        for group in ('requests','dit_rounds'):
            if len(a[group])!=len(b[group]):
                raise RuntimeError('HARD_STOP_periodic_kernel_count_mismatch')
            for left,right in zip(a[group],b[group]):
                for key,value in right.items():
                    if key=='stage_mask':
                        continue
                    if value is None or isinstance(value,bool):
                        if left[key]!=value:
                            raise RuntimeError('HARD_STOP_periodic_kernel_field_mismatch '+key)
                    else:
                        errors.append(abs(left[key]-value)/max(1.,abs(left[key])))
        for key in ('vlm_busy','dit_busy','makespan_s','dit_GB_per_req','dram_GB_per_req'):
            errors.append(abs(a[key]-b[key])/max(1.,abs(a[key])))
        if max(errors)>1e-10 or a['vlm_queue'] ['steady_max_length']!=b['vlm_queue']['steady_max_length']:
            raise RuntimeError('HARD_STOP_periodic_kernel_numeric_mismatch')
        record=dict(index=index,hardware=asdict(hw),mapping=asdict(mp),n=n,
            max_scaled_error=max(errors),requests=b['requests'],rounds=b['dit_rounds'],
            metrics={key:b[key] for key in ('vlm_busy','dit_busy','makespan_s','dit_GB_per_req','dram_GB_per_req')})
        write_json(out/f'case_{index}.json',record)
        records.append(dict(index=index,n=n,max_scaled_error=max(errors)))
        print('Validated',index,n,max(errors),flush=True)
    write_json(out/'status.json',dict(passed=True,cases=records,
        source_sha256=digest(Path(__file__).with_name('v51_periodic.cpp')),
        wrapper_sha256=digest(Path(__file__).with_name('v51_fast.py')),
        library_sha256=digest(library),snapshot=str(snapshot)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True);p.add_argument('--snapshot',default='.native/compute')
    a=p.parse_args();validate(a.out,a.snapshot)
