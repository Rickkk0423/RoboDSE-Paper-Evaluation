"""V5 block-sampled, model-derived traffic and explicit experiment identities."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from v4_replay_prepare import components, select_windows


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def block_indices(first, last, block_bytes, stride=10, phase=0):
    if block_bytes < 64 or block_bytes % 64 or not 0 <= phase < stride:
        raise ValueError('invalid cache-line block sampling')
    lines = block_bytes//64
    start = first//lines
    start += (phase-start) % stride
    blocks = np.arange(start, (last+lines-1)//lines, stride, dtype=np.uint64)
    indexes = (blocks[:,None]*lines + np.arange(lines, dtype=np.uint64)).ravel()
    return indexes[(indexes >= first) & (indexes < last)]


def make_arrays(result, window, wl, *, block_bytes=2048, phase=0):
    segments = [s for s in result['memory_segments'] if s['dram_bytes'] > 0 and
        s['end_s'] > window['start_s'] and s['start_s'] < window['end_s']]
    sizes = {}
    for segment in segments:
        parts = components(segment, wl, result)
        if not np.isclose(sum(p[1] for p in parts), segment['op_total_dram_bytes'], rtol=1e-10):
            raise RuntimeError('HARD_STOP_traffic_reconciliation: component/op bytes differ')
        for key, size, owner, _ in parts:
            if key in sizes and sizes[key] != (size, owner):
                raise RuntimeError('HARD_STOP_traffic_reconciliation: region changed')
            sizes[key] = (size, owner)
    offsets, cursor = {}, 0
    for key in sorted(sizes):
        cursor = (cursor+4095)//4096*4096
        offsets[key] = cursor
        cursor += sizes[key][0]
    chunks = []
    for segment in segments:
        s, e = segment['start_s'], segment['end_s']
        a, b = max(s, window['start_s']), min(e, window['end_s'])
        if b <= a or e <= s:
            continue
        f0, f1 = segment['op_fraction_start'], segment['op_fraction_end']
        total = segment['op_total_dram_bytes']
        start_byte = (f0+(a-s)/(e-s)*(f1-f0))*total
        end_byte = (f0+(b-s)/(e-s)*(f1-f0))*total
        component_start = 0
        for key, size, owner, write in components(segment, wl, result):
            left, right = max(start_byte, component_start), min(end_byte, component_start+size)
            if right > left:
                first = int(np.ceil((left-component_start)/64-1e-8))
                last = int(np.ceil((right-component_start)/64-1e-8))
                indices = block_indices(first,last,block_bytes,phase=phase) if window['window'] == 'W5' else np.arange(first,last,dtype=np.uint64)
                if len(indices):
                    op_bytes = component_start+indices.astype(float)*64
                    times = s+((op_bytes/total-f0)/(f1-f0))*(e-s)
                    scale = .1 if window['window'] == 'W5' else 1.
                    times = np.maximum(0., (times-window['start_s'])*scale*1e9)
                    chunks.append((times, np.full(len(indices),segment['group']=='dit',dtype=np.uint8),
                        indices*64+offsets[key], np.full(len(indices),write,dtype=np.uint8),
                        np.full(len(indices),owner,dtype=np.uint8)))
            component_start += size
    if not chunks:
        raise ValueError('empty window')
    arrays = {key: np.concatenate([c[i] for c in chunks]) for i,key in enumerate(
        ('issue_ns','core','address','write','owner'))}
    order = np.argsort(arrays['issue_ns'],kind='stable')
    arrays = {key: value[order] for key,value in arrays.items()}
    return arrays, [dict(name=k,base=offsets[k],bytes=v[0],owner=v[1]) for k,v in sorted(sizes.items())], cursor


def offered(arrays, launch, *, serial=False):
    if serial:
        result = dict(arrays)
        result['epoch'] = np.r_[0,np.cumsum(arrays['core'][1:] != arrays['core'][:-1])].astype(np.uint32)
        if launch == 'saturated':
            result['issue_ns'] = np.zeros(len(arrays['core']))
        elif launch != 'open':
            raise ValueError('unknown launch')
        return result
    if launch == 'open':
        return arrays
    if launch != 'saturated':
        raise ValueError('unknown launch')
    rank = np.empty(len(arrays['core']),dtype=float)
    for c in (0,1):
        selected = np.flatnonzero(arrays['core']==c)
        rank[selected] = (np.arange(len(selected))+.5)/max(1,len(selected))
    order = np.argsort(rank,kind='stable')
    result = {key:value[order] for key,value in arrays.items()}
    result['issue_ns'] = np.zeros(len(order))
    return result


def prepare_selfcheck(out):
    from vlasim import HWConfig, MapConfig, Simulator, DRAMModel
    from vlasim.neusim_compute import NeuSimTiming
    from vlasim.workload import Pi05Workload
    from v4_replay_prepare import CASES
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    v4 = json.loads(Path('results/v4/p0a_input/manifest.json').read_text())
    c = next(c for c in v4['cases'] if c['name']=='L_serial')
    wl = Pi05Workload()
    result = Simulator(HWConfig(**c['config']['hardware']),MapConfig(**c['config']['mapping']),wl,
        DRAMModel(**c['calibration']['params']),
        NeuSimTiming(Path('.native/compute'),wl,allow_analytical_siglip=True)).run(120,24,record=True,diagnostics=True)
    window = next(w for w in select_windows(result,'serial',1)[0] if w['window']=='W5')
    # LPDDR5 x16 has 1024 columns: one physical row is 2048 bytes.
    traces = []
    for label, size in (('2KB',2048),('one_row',2048)):
        arrays, regions, footprint = make_arrays(result,window,wl,block_bytes=size)
        for launch in ('open','saturated'):
            path = out/f'L_serial_W5_{label}_{launch}.npz'
            data = offered(arrays,launch,serial=True)
            np.savez_compressed(path,**data)
            traces.append(dict(id=path.stem,trace=path.name,trace_sha256=digest(path),
                block_bytes=size,sampling_label=label,launch=launch,window=window,
                bytes_by_stream=[int(np.count_nonzero(data['core']==i))*64 for i in (0,1)],
                regions=regions,footprint_bytes=footprint))
    write_json(out/'manifest.json',dict(case=c,windows=traces,
        source_sha256={str(p):digest(p) for p in (Path(__file__),Path('vlasim/v4_replay_prepare.py'))},
        v4_manifest_sha256=digest('results/v4/p0a_input/manifest.json'),
        protocol='Keep one entire contiguous block out of ten per component, global timestamps /10; '
                 'block interiors preserve consecutive physical addresses. '
                 '2KB and row protocols coincide for this LPDDR5 geometry and are not independent samples.',
        serial_protocol='Preserve original phase order; a later VLM/DiT epoch cannot issue until all callbacks of prior epochs are drained.',
        selfcheck='saturated total throughput / (eta_seq * peak) >= .90 for both block definitions; '
                  'open demand feasibility reported separately, not mistaken for saturated capacity'))


if __name__ == '__main__':
    prepare_selfcheck('results/v5/selfcheck_input_v2')
