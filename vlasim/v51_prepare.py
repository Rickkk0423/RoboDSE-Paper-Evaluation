"""Freeze V5.1 stage-one complete-period block controls before native execution."""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import shutil
import sys

import numpy as np

from v5_protocol import digest, make_arrays, offered, write_json
from v4_replay_prepare import select_windows
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def seq_arrays(kb, total=4*1024**2):
    lines = total//64
    tile = kb*1024//64
    i = np.arange(lines,dtype=np.uint64)
    return dict(issue_ns=np.zeros(lines),core=np.zeros(lines,dtype=np.uint8),
                address=(i//tile*tile*2+i%tile)*64,write=np.zeros(lines,dtype=np.uint8))


def prepare(out):
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    frozen = json.loads(Path('results/v5_1/catalog_local/catalog.json').read_text())
    v4 = json.loads(Path('results/v4/p0a_input/manifest.json').read_text())
    reference = next(c for c in v4['cases'] if c['name']=='L_serial')
    wl = Pi05Workload()
    provider = NeuSimTiming('.native/compute',wl,allow_analytical_siglip=True)
    seqs = []
    for kb in (4,64,1024):
        path = out/f'seq_{kb}KB.npz'
        np.savez_compressed(path,**seq_arrays(kb))
        seqs.append(dict(id=f'seq_{kb}KB',path=path.name,sha256=digest(path)))
    items = []
    for row in frozen['memories']:
        config, geometry = row['config'], row['geometry']
        hw = HWConfig(**{**reference['config']['hardware'],'dram_bw':geometry['peak_GBps']*1e9})
        mp = MapConfig(**reference['config']['mapping'])
        result = Simulator(hw,mp,wl,DRAMModel(**reference['calibration']['params']),provider).run(
            120,24,record=True,diagnostics=True)
        window = next(w for w in select_windows(result,'serial',1)[0] if w['window']=='W5')
        levels = []
        for level in (1,2):
            size = geometry['row_spans'][f'level{level}_bytes']
            arrays, regions, footprint = make_arrays(result,window,wl,block_bytes=size)
            arrays = offered(arrays,'saturated',serial=True)
            path = out/f'{config["id"]}_level{level}.npz'
            np.savez_compressed(path,**arrays)
            levels.append(dict(level=level,block_bytes=size,path=path.name,sha256=digest(path),
                window=window,regions=regions,footprint_bytes=footprint,
                bytes_by_stream=[int(np.count_nonzero(arrays['core']==i))*64 for i in (0,1)]))
            print(config['id'],level,size,flush=True)
        items.append(dict(config=config,geometry=geometry,levels=levels,
            hardware=asdict(hw),mapping=asdict(mp),
            generation_calibration=reference['calibration'],
            generation_scope='Reference DRAM params only determine source event times; saturated '
                'native controls have zero issue times, original serial phase order, and drain barriers.'))
    for source in (Path(__file__),Path('vlasim/v5_protocol.py'),Path('vlasim/v4_replay_prepare.py')):
        shutil.copy2(source,out/source.name)
    write_json(out/'manifest.json',dict(items=items,seq_traces=seqs,
        legacy_hbm_calibration=next(c for c in v4['cases'] if c['name']=='H_serial')['calibration'],
        catalog_sha256=digest('results/v5_1/catalog_local/catalog.json'),
        amendment_sha256=digest('/Users/mr.meeseeks/Downloads/NEXT_STEPS_V5_1_AMENDMENT.md'),
        protocol='One entire contiguous block in ten per component, physical addresses unchanged, '
                 'timestamps /10 then saturated at zero; original serial epoch drain barriers.',
        sources_sha256={p.name:digest(p) for p in out.glob('*.py')}))


if __name__=='__main__':
    prepare('results/v5_1/stage1_input')
