"""Validated periodic kernel using unchanged Simulator op templates and NeuSim costs."""
import ctypes as ct
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import numpy as np

from vlasim import Simulator


class NativeOp(ct.Structure):
    _fields_=[('compute',ct.c_double),('bytes',ct.c_double),('weight',ct.c_double),
              ('kv',ct.c_double),('attention',ct.c_int)]


def build(out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    path=out/('periodic.dylib' if sys.platform=='darwin' else 'periodic.so')
    subprocess.run(['c++','-O2','-ffp-contract=off','-std=c++17','-shared','-fPIC',
                    str(Path(__file__).with_name('v51_periodic.cpp')),'-o',str(path)],check=True)
    return path


class Periodic:
    def __init__(self,hw,mp,wl,dram,provider,library):
        self.hw,self.mp,self.wl,self.dram=hw,mp,wl,dram
        self.reference=Simulator(hw,replace(mp,vlm_launch='periodic',launch_period_s=1.),wl,dram,provider)
        self.k=self.reference.k
        def ops(sequence,group):
            output=[]
            for op in sequence:
                compute=provider(op,group,self.reference.g[group].peak,hw) if provider else (
                    op.flops/max(op.util,1e-9)/self.reference.g[group].peak)
                kv=0.
                if not self.reference.kv_on_chip:
                    kv=wl.kv_layer_bytes if group=='vlm' and op.name!='siglip' else (
                        op.dram_bytes if op.name.endswith('_attn') else 0.)
                output.append(NativeOp(compute,op.dram_bytes,op.weight_bytes,kv,
                                       int(op.name.endswith('_attn'))))
            return output
        v=ops(self.reference._vlm_ops(),'vlm')
        self.v=(NativeOp*len(v))(*v)
        d,offsets,lengths=[],[],[]
        for mask in range(1<<self.k):
            offsets.append(len(d))
            row=ops(self.reference._dit_round_ops([s if mask&(1<<s) else None
                for s in range(self.k)]),'dit') if mask else []
            lengths.append(len(row));d.extend(row)
        self.d=(NativeOp*len(d))(*d)
        self.offsets=(ct.c_int*len(offsets))(*offsets)
        self.lengths=(ct.c_int*len(lengths))(*lengths)
        self.lib=ct.CDLL(str(Path(library).resolve()))
        array=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
        self.lib.periodic_run.argtypes=[ct.c_int]*4+[ct.c_double]*4+[ct.c_int,ct.c_double,
            ct.POINTER(NativeOp),ct.c_int,ct.POINTER(NativeOp),ct.POINTER(ct.c_int),
            ct.POINTER(ct.c_int),array,array,array]
        self.lib.periodic_run.restype=ct.c_int
        self.lib.periodic_error.restype=ct.c_char_p

    def run(self,period,n=480,warmup=None):
        warmup=n//5 if warmup is None else warmup
        req=np.zeros((n,4));raw=np.zeros((n+self.k,12));summary=np.zeros(13)
        code=self.lib.periodic_run(n,warmup,self.k,int(self.mp.mode=='serial'),period,
            self.hw.dram_bw,self.dram.eta_seq,self.dram.eta_mix,
            int(self.mp.bw_policy=='vlm_priority'),self.mp.stream_partition or -1.,
            self.v,len(self.v),self.d,self.offsets,self.lengths,req,raw,summary)
        if code:
            raise RuntimeError(self.lib.periodic_error().decode())
        count=int(summary[6]);stop=n-self.k-2
        rows=[dict(request_id=i,obs_s=float(r[0]),vlm_start_s=float(r[1]),vlm_end_s=float(r[2]),
            done_s=float(r[3]),L_s=float(r[3]-r[0]),S_s=float(r[3]-req[i-1,3]) if i else None,
            vlm_wait_s=float(r[1]-r[0]),steady_state=warmup<=i<stop) for i,r in enumerate(req)]
        rounds=[]
        for r in raw[:count]:
            rounds.append(dict(zip(('start_s','end_s','duration_s','compute_s','exposed_memory_s',
                'linear_s','attention_s','dram_bytes','weight_bytes','wait_before_s'),map(float,r[:10])),
                stage_mask=int(r[10]),tail_drain=bool(r[11])))
        return dict(requests=rows,dit_rounds=rounds,makespan_s=float(summary[0]),
            vlm_busy=float(summary[1]),dit_busy=float(summary[2]),
            dram_GB_per_req=float(summary[3]+summary[4]),dit_GB_per_req=float(summary[4]),
            vlm_queue=dict(steady_max_length=int(summary[5])),
            measurement_window_s=[float(req[warmup,3]),float(req[stop-1,3])],
            steady_vlm_busy=float(summary[7]),steady_dit_busy=float(summary[8]),
            steady_vlm_GBps=float(summary[9]/1e9),steady_dit_GBps=float(summary[10]/1e9),
            steady_KV_GBps=float((summary[11]+summary[12])/1e9),
            kv_on_chip=self.reference.kv_on_chip,act_on_chip=self.reference.act_on_chip,
            sram_ok=self.reference.sram_ok,dram_version=self.dram.version,
            execution_engine='v51-periodic-template-kernel')
