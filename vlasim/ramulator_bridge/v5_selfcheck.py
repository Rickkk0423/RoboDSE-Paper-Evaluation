"""Execute frozen V5 block-sampling controls; preserve every result and native stat."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

import yaml

from case_v3_p0 import digest, export, MEMORIES
from run_native import load_backend
from v5_native import build, execute


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--backend',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--shard',type=int,default=0)
    ap.add_argument('--shards',type=int,default=1)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),Path(__file__).with_name('v5_driver.cpp'),Path(__file__).with_name('v5_native.py'),
             Path(__file__).with_name('case_v3_p0.py'),Path(__file__).with_name('channel_frontend.py'),Path(__file__).with_name('run_native.py')]
    for source in sources:
        shutil.copy2(source,args.out/source.name)
    manifest=json.loads((args.input/'manifest.json').read_text())
    windows=[w for i,w in enumerate(manifest['windows']) if i%args.shards==args.shard]
    frozen=dict(input_manifest_sha256=digest(args.input/'manifest.json'),windows=windows,
                source_hashes={p.name:digest(p) for p in sources})
    (args.out/'manifest.json').write_text(json.dumps(frozen,indent=2)+'\n')
    Ramulator,_=load_backend(args.backend.resolve())
    library=args.backend.resolve()/'build'/('libneusim_ramulator_bridge'+('.dylib' if sys.platform=='darwin' else '.so'))
    driver=build(args.out)
    config=MEMORIES['M-L256']
    geometry=export(config,args.out/'dram.yaml',mapper='MOP4CLXOR')
    hbm=dict(standard='HBM2',channels=8,organization='HBM2_8Gb',timing='HBM2_2000Mbps')
    hbm_geometry=export(hbm,args.out/'large_hbm.yaml',mapper='MOP4CLXOR')
    if hbm_geometry['capacity_bytes'] < 8*1024**3:
        raise RuntimeError('large HBM identity below requested capacity')
    rows=[]
    for window in windows:
        trace=args.input/window['trace']
        if digest(trace)!=window['trace_sha256']:
            raise RuntimeError('frozen trace hash mismatch')
        started=time.monotonic()
        with Ramulator(args.out/'dram.yaml',library=library) as memory:
            native=execute(memory,trace,channels=16,issue_width=8,driver=driver,library=library)
            stats=args.out/(window['id']+'_stats.yaml')
            memory.finalize(stats)
        raw=yaml.safe_load(stats.read_text())['memory_system']
        reads,writes=raw['total_num_read_requests'],raw['total_num_write_requests']
        controllers=raw['controller']
        served_reads=sum(c.get('num_read_reqs_served',0)+c.get('num_read_reqs_forwarded',0) for c in controllers)
        served_writes=sum(c.get('num_write_reqs_served',0)+c.get('num_write_reqs_coalesced',0) for c in controllers)
        if reads+writes!=native['completed'] or reads!=served_reads or writes!=served_writes or native['logical_bytes']!=sum(window['bytes_by_stream']):
            raise RuntimeError('HARD_STOP_native_accounting_mismatch')
        eta=manifest['case']['calibration']['params']['eta_seq']
        end=max(v for v in native['last_completion_ns'] if v is not None)
        ratio=native['logical_bytes']/end/(eta*geometry['peak_GBps'])
        row=dict(window=window,native=native,total_over_seq_reference=ratio,
            selfcheck_pass=ratio>=.90 if window['launch']=='saturated' else None,
            geometry=geometry,large_hbm_identity=dict(config=hbm,geometry=hbm_geometry),
            wall_seconds=time.monotonic()-started,accounting_ok=True,
            backend_identity=dict(source_manifest_sha256=digest(args.backend/'source_manifest.json'),
                                  bridge_sha256=digest(library)),driver_sha256=digest(driver))
        (args.out/(window['id']+'.json')).write_text(json.dumps(row,indent=2)+'\n')
        print(window['id'],round(ratio,6),row['wall_seconds'],flush=True)
        rows.append(window['id'])
    (args.out/'completed.json').write_text(json.dumps(dict(windows=rows))+'\n')


if __name__=='__main__':
    main()
