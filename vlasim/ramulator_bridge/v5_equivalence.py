"""Native equivalence probes before enabling the V5 real-cycle issue driver."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

from case_v3_p0 import digest, export, MEMORIES
from run_native import load_backend
from v4_replay_native import execute_arrays
from v5_native import build, execute


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    Ramulator,_ = load_backend(args.backend.resolve())
    library = args.backend.resolve()/'build'/('libneusim_ramulator_bridge'+('.dylib' if sys.platform=='darwin' else '.so'))
    driver = build(args.out)
    rows = []
    for name in ('M-H256','M-L256','M-L512'):
        config = MEMORIES[name]
        for bg in (False,True):
            label = name+('_bg' if bg else '_plain')
            path = args.out/(label+'.yaml')
            geometry = export(config,path,mapper='MOP4CLXOR')
            n = 8192
            trace = args.out/(label+'.npz')
            np.savez(trace,issue_ns=np.arange(n)//512*300.,core=(np.arange(n)//17%2).astype(np.uint8),
                address=np.arange(n,dtype=np.uint64)*64,
                write=(np.arange(n)%19==0).astype(np.uint8),owner=(np.arange(n)//17%2).astype(np.uint8))
            kwargs = dict(channels=config['channels'],issue_width=16 if name=='M-L512' else 8,
                          bg_geometry=geometry['mop_geometry'] if bg else None)
            with Ramulator(path,library=library) as memory:
                old = execute_arrays(memory,trace,**kwargs)
                memory.finalize(args.out/(label+'_reference_stats.yaml'))
            with Ramulator(path,library=library) as memory:
                new = execute(memory,trace,driver=driver,library=library,**kwargs)
                memory.finalize(args.out/(label+'_v5_stats.yaml'))
            keys = set(old)-{'frontend_version'}
            differences = [key for key in keys if old[key]!=new[key]]
            row = dict(id=label,differences=differences,native=new,
                geometry=geometry,reference_stats_sha256=digest(args.out/(label+'_reference_stats.yaml')),
                v5_stats_sha256=digest(args.out/(label+'_v5_stats.yaml')))
            rows.append(row)
            if differences:
                raise RuntimeError(f'HARD_STOP_driver_equivalence: {label}: {differences}')
    (args.out/'status.json').write_text(json.dumps(dict(exact=True,comparisons=rows,
        driver_source_sha256=digest(Path(__file__).with_name('v5_driver.cpp')),
        driver_library_sha256=digest(driver)),indent=2)+'\n')
    print('6 exact native driver comparisons passed',flush=True)


if __name__=='__main__':
    main()
