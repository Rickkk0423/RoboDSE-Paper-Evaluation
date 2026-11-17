"""Freeze model-derived VLA windows with event-rate traffic and per-layer layout."""
import argparse
from dataclasses import asdict
import gzip
import itertools
import json
from pathlib import Path
import re
import shutil

import numpy as np

from case_v3_main import digest, write_json
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


CASES = (
    ('H_serial', 'M-H256', 8, 'serial', 8, 1, False),
    ('H_k1', 'M-H256', 8, 'pipelined', 4, 1, False),
    ('H_k2', 'M-H256', 8, 'pipelined', 6, 2, False),
    ('H_bg_k2', 'M-H256', 8, 'pipelined', 5, 2, True),
    ('L_serial', 'M-L256', 8, 'serial', 8, 1, False),
    ('L_bg_k2', 'M-L256', 8, 'pipelined', 4, 2, True),
    ('L512_k3', 'M-L512', 16, 'pipelined', 8, 3, False),
    ('L512_bg_k3', 'M-L512', 16, 'pipelined', 7, 3, True),
)


def intervals(timeline, group=None, min_batch=1):
    spans = sorted((s, e) for s, e, g, _, b, req in timeline if
                   (group is None or g == group) and (g != 'dit' or len(req) >= min_batch))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1e-12:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def intersect(left, right):
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        a, b = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if b > a:
            out.append((a, b))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return out


def difference(left, right):
    result = []
    for a, b in left:
        cursor = a
        for c, d in right:
            if d <= cursor:
                continue
            if c >= b:
                break
            if c > cursor:
                result.append((cursor, min(c, b)))
            cursor = max(cursor, d)
            if cursor >= b:
                break
        if cursor < b:
            result.append((cursor, b))
    return result


def select_windows(result, mode, k, duration=.0005):
    lo, hi = result['measurement_window_s']
    bounds = [(lo, hi)]
    v = intersect(intervals(result['timeline'], 'vlm'), bounds)
    d = intersect(intervals(result['timeline'], 'dit'), bounds)
    choices = {'W1': difference(v, d), 'W2': difference(d, v)}
    if mode == 'pipelined' and k == 1:
        choices['W3'] = intersect(v, d)
    if mode == 'pipelined' and k == 2:
        choices['W4'] = intersect(v, intersect(intervals(result['timeline'], 'dit', 2), bounds))
    windows, missing = [], []
    for name in ('W1', 'W2', 'W3', 'W4'):
        if name not in choices:
            missing.append(dict(window=name, reason='not applicable to this mode/k'))
            continue
        adequate = [(a, b) for a, b in choices[name] if b - a >= duration]
        if not adequate:
            missing.append(dict(window=name, reason='no continuous qualifying .5ms steady interval'))
            continue
        a, b = adequate[len(adequate) // 2]
        start = (a + b - duration) / 2
        windows.append(dict(window=name, start_s=start, end_s=start + duration, sampling=1, time_scale=1.))
    if mode == 'serial':
        trace = result['trace']
        a, b = trace[len(trace) // 2]
    else:
        rounds = [r for r in result['dit_rounds'] if lo <= r['start_s'] and r['end_s'] <= hi]
        middle = len(rounds) // 2
        a = rounds[middle]['start_s']
        b = rounds[middle + 1]['start_s']
    windows.append(dict(window='W5', start_s=a, end_s=b, sampling=10, time_scale=.1))
    return windows, missing


def components(segment, wl, result):
    name, reqs = segment['op_name'], segment['request_ids']
    c = wl.c
    if name == 'siglip':
        return [('weight_vlm_siglip', int(c.siglip_params * c.w_bytes), 0, False)]
    layer = int(re.search(r'_l(\d+)', name).group(1))
    if segment['group'] == 'vlm':
        parts = [(f'weight_vlm_l{layer:02}', int(wl.vlm_layer_params * c.w_bytes), 0, False)]
        if not result['kv_on_chip']:
            parts.append((f'kv_req{reqs[0]:04}_l{layer:02}', int(wl.kv_layer_bytes), 1, True))
        if not result['act_on_chip']:
            size = int(wl.vlm_spill_layer_bytes / 2)
            parts.extend([(f'act_req{reqs[0]:04}_l{layer:02}', size, 0, False),
                          (f'act_req{reqs[0]:04}_l{layer:02}', size, 0, True)])
        return parts
    if name.endswith('_lin'):
        return [(f'weight_dit_l{layer:02}', int(wl.dit_layer_params * c.w_bytes), 1, False)]
    return [] if result['kv_on_chip'] else [(f'kv_req{req:04}_l{layer:02}', int(wl.kv_layer_bytes), 1, False) for req in reqs]


def make_arrays(result, window, wl):
    segments = [s for s in result['memory_segments'] if s['dram_bytes'] > 0 and
                s['end_s'] > window['start_s'] and s['start_s'] < window['end_s']]
    sizes = {}
    for segment in segments:
        parts = components(segment, wl, result)
        if not np.isclose(sum(p[1] for p in parts), segment['op_total_dram_bytes']):
            raise ValueError('op component bytes disagree with actual simulator')
        for key, size, owner, _ in parts:
            if key in sizes and sizes[key] != (size, owner):
                raise ValueError('logical region size/ownership changed')
            sizes[key] = (size, owner)
    offsets, cursor = {}, 0
    for key in sorted(sizes):
        cursor = (cursor + 4095) // 4096 * 4096
        offsets[key] = cursor
        cursor += sizes[key][0]
    chunks = []
    for segment in segments:
        s, e = segment['start_s'], segment['end_s']
        if e <= s:
            continue
        a, b = max(s, window['start_s']), min(e, window['end_s'])
        f0, f1 = segment['op_fraction_start'], segment['op_fraction_end']
        total = segment['op_total_dram_bytes']
        start_byte = (f0 + (a - s) / (e - s) * (f1 - f0)) * total
        end_byte = (f0 + (b - s) / (e - s) * (f1 - f0)) * total
        component_start = 0
        for key, size, owner, write in components(segment, wl, result):
            left, right = max(start_byte, component_start), min(end_byte, component_start + size)
            if right <= left:
                component_start += size
                continue
            first = int(np.ceil((left - component_start) / 64 - 1e-8))
            last = int(np.ceil((right - component_start) / 64 - 1e-8))
            sample = window['sampling']
            first = ((first + sample - 1) // sample) * sample
            indexes = np.arange(first, last, sample, dtype=np.uint64)
            if len(indexes):
                op_bytes = component_start + indexes.astype(float) * 64
                times = s + ((op_bytes / total - f0) / (f1 - f0)) * (e - s)
                times = np.maximum(0., (times - window['start_s']) * window['time_scale'] * 1e9)
                chunks.append((times, np.full(len(indexes), segment['group'] == 'dit', dtype=np.uint8),
                    indexes * 64 + offsets[key], np.full(len(indexes), write, dtype=np.uint8),
                    np.full(len(indexes), owner, dtype=np.uint8)))
            component_start += size
    if not chunks:
        raise ValueError('empty replay window')
    arrays = {name: np.concatenate([chunk[i] for chunk in chunks]) for i, name in
              enumerate(('issue_ns', 'core', 'address', 'write', 'owner'))}
    order = np.argsort(arrays['issue_ns'], kind='stable')
    arrays = {k: v[order] for k, v in arrays.items()}
    regions = [dict(name=k, base=offsets[k], bytes=v[0], bg_owner=v[1]) for k, v in sorted(sizes.items())]
    return arrays, regions, cursor


def closed_prediction(counts, peak, dram):
    remaining = {str(i): b for i, b in enumerate(counts)}
    done, t = [None, None], 0.
    while any(b > 0 for b in remaining.values()):
        demands = {key: peak if b > 0 else 0. for key, b in remaining.items()}
        rates = dram.allocate(peak, demands, 'fair')
        dt = min(b / rates[key] for key, b in remaining.items() if b > 0)
        t += dt
        for key in remaining:
            if remaining[key] > 0:
                remaining[key] = max(0., remaining[key] - rates[key] * dt)
                if remaining[key] < 1e-5:
                    remaining[key] = 0.
                    done[int(key)] = t * 1e9
    return done


def prepare(args):
    args.out.mkdir(parents=True, exist_ok=False)
    source_dir = args.out / 'executed_sources'
    source_dir.mkdir()
    sources = [Path(__file__)] + list((Path(__file__).parent / 'vlasim').glob('*.py'))
    for source in sources:
        rel = source.relative_to(Path(__file__).parent)
        target = source_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(args.spec, args.out / 'NEXT_STEPS_V4.md')
    memories = json.loads((args.native / 'isolation_report.json').read_text())
    wl = Pi05Workload()
    provider = NeuSimTiming(args.snapshot, wl, allow_analytical_siglip=True)
    windows, cases, unavailable = [], [], []
    for name, memory, cores, mode, split, k, bg in CASES:
        calib_path = args.v3 / (f'dram_v3_{memory}_bg_saturated_fit.json' if bg else
            f'dram_v3_{memory}_mop4_width{16 if memory == "M-L512" else 8}.json')
        calib = json.loads(calib_path.read_text())
        dram = DRAMModel(**calib['params'], version=calib['version'])
        peak = memories['memories'][memory]['peak_GBps']
        capacity = next(r['geometry']['capacity_bytes'] for r in memories['runs'] if r['memory'] == memory)
        hw = HWConfig(n_cores=cores, sram_mb=64, local_kb=2048, dram_bw=peak * 1e9,
                      slice_mode=False, dram_priority=False)
        mp = MapConfig(mode=mode, vlm_cores=split, dit_stages=k, bw_policy='fair')
        cfg = dict(hardware=asdict(hw), mapping=asdict(mp), memory=memory, bg=bg)
        cid = __import__('hashlib').sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
        cases.append(dict(name=name, config_id=cid, config=cfg, calibration=calib,
                          calibration_sha256=digest(calib_path)))
        result = Simulator(hw, mp, wl=wl, dram=dram, compute_time_fn=provider).run(120, 24, record=True, diagnostics=True)
        choices, missing = select_windows(result, mode, k)
        unavailable.extend(dict(case=name, **row) for row in missing)
        with gzip.open(args.out / (name + '_timeline.json.gz'), 'wt') as stream:
            json.dump(dict(timeline=result['timeline'], memory_segments=result['memory_segments'],
                           dit_rounds=result['dit_rounds'], measurement_window_s=result['measurement_window_s']), stream)
        for selection in choices:
            arrays, regions, footprint = make_arrays(result, selection, wl)
            if footprint * (2 if bg else 1) > capacity:
                unavailable.append(dict(case=name, window=selection['window'], reason='full touched-layer layout exceeds calibrated native capacity',
                    footprint_bytes=footprint, bg_capacity_factor=2 if bg else 1, capacity_bytes=capacity))
                continue
            counts = [int(np.count_nonzero(arrays['core'] == c)) * 64 for c in (0, 1)]
            original_times = arrays['issue_ns'].copy()
            first, finish = [], []
            for c in (0, 1):
                indexes = np.flatnonzero(arrays['core'] == c)
                if not len(indexes):
                    first.append(None); finish.append(None)
                else:
                    t = original_times[indexes]
                    first.append(float(t[0]))
                    # A final cache line completes at most one line service later.
                    gap = (selection['end_s'] - selection['start_s']) * selection['time_scale'] * 1e9
                    finish.append(min(float(t[-1]) + 64 / (peak * dram.eta_seq), gap))
            for launch in ('open', 'saturated'):
                trace_id = name + '_' + selection['window'] + '_' + launch
                trace = args.out / (trace_id + '.npz')
                if launch == 'open':
                    offered = arrays
                    predicted, predicted_first = finish, first
                else:
                    rank = np.empty(len(arrays['core']), dtype=float)
                    for c in (0, 1):
                        indexes = np.flatnonzero(arrays['core'] == c)
                        rank[indexes] = (np.arange(len(indexes)) + .5) / max(len(indexes), 1)
                    order = np.argsort(rank, kind='stable')
                    offered = {key: value[order] for key, value in arrays.items()}
                    offered['issue_ns'] = np.zeros(len(order), dtype=float)
                    predicted = closed_prediction(counts, peak * 1e9, dram)
                    predicted_first = [0. if b else None for b in counts]
                np.savez_compressed(trace, **offered)
                windows.append(dict(id=trace_id, case=name, config_id=cid, memory=memory, bg=bg,
                    window=selection['window'], selection=selection, launch=launch, peak_GBps=peak,
                    eta_seq=dram.eta_seq, eta_mix=dram.eta_mix, prediction_finish_ns=predicted,
                    prediction_first_offer_ns=predicted_first, bytes_by_stream=counts,
                    trace=trace.name, trace_sha256=digest(trace), regions=regions, footprint_bytes=footprint))
        print(name, 'windows frozen so far', len(windows), flush=True)
    manifest = dict(spec_sha256=digest(args.spec), cases=cases, windows=windows, unavailable=unavailable,
        source_hashes={str(p.relative_to(Path(__file__).parent)): digest(p) for p in sources},
        compute_snapshot_sha256=digest(args.snapshot / 'source_manifest.json'),
        native_reference_sha256=digest(args.native / 'isolation_report.json'),
        protocol=dict(window_duration_s=.0005, issue_widths={'M-H256':8, 'M-L256':8, 'M-L512':16},
            outstanding=512, transaction_bytes=32, mapper='MOP4CLXOR', controller='FRFCFS/Open',
            W5='one observed post-warmup cycle, every10th64Bline and time scaled1/10; preserves nominal demand but sampled address stride changes locality; W5 duration may exceed1ms',
            placement='window-local compacted, full touched layer regions, 4KiB alignment; shared KV keeps identical writer/reader physical address and belongs to BG1',
            open='event-progress rates, native callbacks do not feed back into model schedule',
            saturated='same per-stream addresses/order and byte counts, all offered at0 with ratio-weighted line interleave; prediction fluid fair infinite demand'),
        scope='Model-derived estimated-shape traffic and explicit experimental placement, NOT independent execution capture or verified checkpoint layout. No parameter fitting. Capacity/coverage omissions remain failures of complete requested coverage.',
        acceptance='every measured per-stream duration error <=10%; mean of all absolute per-stream errors <=5%; report coverage gaps separately and do not promote incomplete dynamic validation')
    write_json(args.out / 'manifest.json', manifest)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--spec', type=Path, required=True)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--native', type=Path, required=True)
    ap.add_argument('--v3', type=Path, required=True)
    prepare(ap.parse_args())


if __name__ == '__main__':
    main()
