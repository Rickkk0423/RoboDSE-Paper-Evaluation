"""Complete same-split controls when optimization pruned every pipeline allocation."""
from dataclasses import asdict,replace
import json
from pathlib import Path

from case_v3_main import write_csv
from v51_dse import evaluate,lower_bound,semantic_key
from v51_fast import Periodic
from v51_package import read_csv
from v51_workflow import ROOT,load
from v5_protocol import digest,write_json
from vlasim import DRAMModel,HWConfig,MapConfig
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def supplement():
    root=ROOT/'dse/ablation_supplement';root.mkdir(exist_ok=True)
    calibrations=load(ROOT/'calibration.json');wl=Pi05Workload()
    provider=NeuSimTiming('.native/compute',wl,allow_analytical_siglip=True)
    library=ROOT/'dse'/('periodic.dylib' if __import__('sys').platform=='darwin' else 'periodic.so')
    output=[]
    completed=sorted((ROOT/'dse/shards').glob('*/status.json'))
    for path in completed:
        shard=path.parent
        for row in read_csv(shard/'k_ablation.csv'):
            if not row['status'].startswith('N/A') or int(row['n_cores'])<2 or row['local_kb']!='512':
                continue
            memory=row['memory'];cal=calibrations[memory];bg=row['bg']=='True'
            params=cal['baseline']['bg' if bg else 'plain']['params'] if row['model']=='v3_form' else cal['params']['vla_bg' if bg else 'vla_plain']
            dram=DRAMModel(**params,version=f'V5.1_supplement_{memory}')
            hw=HWConfig(n_cores=int(row['n_cores']),sram_mb=float(row['sram_mb']),local_kb=512,
                dram_bw=cal['geometry']['peak_GBps']*1e9,slice_mode=False,dram_priority=False)
            choices=[MapConfig(vlm_cores=split,dit_stages=k) for split in range(1,hw.n_cores) for k in (1,2,3)]
            selected=min(choices,key=lambda m:(lower_bound(hw,m,wl),m.vlm_cores,m.dit_stages))
            for k,batching in ((1,True),(2,True),(3,True),(2,False),(3,False)):
                mp=replace(selected,dit_stages=k,dit_batching=batching,vlm_launch='periodic',launch_period_s=1.)
                engine=Periodic(hw,mp,wl,dram,provider,library);semantic=semantic_key(engine)
                target=root/'evaluations'/semantic;result=evaluate(engine,target)
                entry={**row,**asdict(mp),'phase':'same_split_control_not_optimization',
                    'selected_split':selected.vlm_cores,'status':result['search']['status'],
                    'Tmin_s':result['search']['Tmin_s'],'semantic_id':semantic,
                    'fallback_allocation_selection':'All pipelines were optimization-pruned, NOT proven infeasible. '
                        'Choose split with smallest analytical throughput lower bound, ties split then k. '
                        'Run all k controls at this split without adding optimization candidates.',
                    'raw':str((target/'requests.npz').relative_to(ROOT)),
                    'pruning_scope':'Supplemental required control; original optimization prune and evidence unchanged.'}
                if result['curve']:
                    point=result['curve'][0]
                    entry.update(point['metrics'],L_s=point['gate']['L_mean_s'],S_s=point['gate']['S_mean_s'],
                        curve_gate=point['gate']['pass_gate'])
                output.extend(dict(entry,local_kb=local,hardware_id=f'{memory}_c{hw.n_cores}_s{row["sram_mb"]}_p{local}') for local in (512,2048))
    write_csv(root/'controls.csv',output)
    write_json(root/'status.json',dict(rows=len(output),source_sha256=digest(__file__),input_completed_shards=len(completed),
        expected_input_shards=80,
        controls_sha256=digest(root/'controls.csv'),scope='Complete ablation only; never retroactively alter optimization pruning/frontiers.'))
    print('Supplemental ablation rows',len(output),flush=True)


if __name__=='__main__':
    supplement()
