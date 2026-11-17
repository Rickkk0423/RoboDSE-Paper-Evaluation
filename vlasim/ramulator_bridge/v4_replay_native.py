"""Native replay of frozen model-derived VLA traffic; no DRAM parameter fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

from case_v3_p0 import MEMORIES, digest, export
from channel_frontend import VERSION, channel_for, partition_address
from run_native import load_backend


def execute_arrays(memory, trace, *, channels, issue_width, bg_geometry=None,
                   outstanding=512, max_cycles=200_000_000):
    """Per-channel FIFO/RR, identical arbitration to v3, with completion per stream."""
    with np.load(trace) as data:
        issue = np.repeat(data['issue_ns'], 2)
        core = np.repeat(data['core'], 2)
        address = np.repeat(data['address'], 2) + np.tile(np.array([0, 32], dtype=np.uint64), len(data['core']))
        write = np.repeat(data['write'], 2)
        owner = np.repeat(data['owner'], 2) if 'owner' in data.files else core
    if memory.tx_bytes != 32:
        raise ValueError('this replay explicitly requires the calibrated native32 payload')
    if len(issue) < 10 or not np.all(np.isfinite(issue)) or np.any(issue < 0) or np.any(np.diff(issue) < 0):
        raise ValueError('trace must have sorted finite issue timestamps')
    if not np.isin(core, [0, 1]).all():
        raise ValueError('only VLM and DiT stream IDs are allowed')
    if bg_geometry is not None:
        address = np.fromiter((partition_address(int(a) // 32, int(c), channels, 32,
                                                mop_geometry=bg_geometry)
                               for a, c in zip(address, owner)), dtype=np.uint64, count=len(address))
    if int(address.max()) + 32 > memory.capacity_bytes:
        raise ValueError('physical window placement exceeds native device capacity')
    channel_ids = (address // 32) & (channels - 1)
    queues = [np.flatnonzero(channel_ids == ch) for ch in range(channels)]
    cursors = [0] * channels
    pending = {}
    cycle = cursor = accepted = rejected = 0
    completed = [0, 0]
    offered = [int(np.count_nonzero(core == c)) for c in (0, 1)]
    first_offer = [float(issue[np.flatnonzero(core == c)[0]]) if offered[c] else None for c in (0, 1)]
    first_done, last_done = [None, None], [None, None]
    address_hash = hashlib.sha256(address.tobytes() + core.tobytes()).hexdigest()
    while accepted < len(issue) or pending:
        for rid, when in memory.completions():
            if rid not in pending:
                raise RuntimeError('unknown/duplicate native callback')
            c, sent = pending.pop(rid)
            if when < sent:
                raise RuntimeError('completion before issue')
            ns = when * memory.tck_ns
            first_done[c] = ns if first_done[c] is None else min(first_done[c], ns)
            last_done[c] = ns if last_done[c] is None else max(last_done[c], ns)
            completed[c] += 1
        if accepted == len(issue) and not pending:
            break
        if cycle >= max_cycles:
            raise RuntimeError(f'native cycle budget exhausted: {accepted}/{len(issue)}')
        blocked = set()
        successes = 0
        now = cycle * memory.tck_ns
        while successes < issue_width and len(pending) < outstanding:
            progress = False
            for _ in range(channels):
                ch = cursor
                cursor = (cursor + 1) % channels
                pos = cursors[ch]
                if ch in blocked or pos == len(queues[ch]):
                    continue
                index = int(queues[ch][pos])
                if issue[index] > now + 1e-9:
                    continue
                c = int(core[index])
                if not memory.send(accepted, bool(write[index]), int(address[index]), c):
                    rejected += 1
                    blocked.add(ch)
                    continue
                pending[accepted] = (c, cycle)
                accepted += 1
                cursors[ch] += 1
                successes += 1
                progress = True
                break
            if not progress:
                break
        memory.tick()
        cycle += 1
    if completed != offered or sum(completed) != accepted:
        raise RuntimeError('per-stream offered/accepted/completed accounting mismatch')
    return dict(accepted=accepted, completed=sum(completed), stream_transactions=completed,
                cycles=cycle, tck_ns=memory.tck_ns, logical_bytes=accepted * 32,
                first_offer_ns=first_offer, first_completion_ns=first_done, last_completion_ns=last_done,
                rejected_attempts=rejected, mapped_transactions_sha256=address_hash,
                frontend_version=VERSION, issue_width=issue_width, outstanding=outstanding)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--backend', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--shard', type=int, default=0)
    ap.add_argument('--shards', type=int, default=1)
    args = ap.parse_args()
    manifest_path = args.input / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), Path(__file__).with_name('case_v3_p0.py'),
               Path(__file__).with_name('channel_frontend.py'), Path(__file__).with_name('run_native.py')]
    frozen = args.out / 'executed_sources'
    frozen.mkdir()
    import shutil
    for source in sources:
        shutil.copy2(source, frozen / source.name)
    run_manifest = dict(input_manifest_sha256=digest(manifest_path), shard=args.shard, shards=args.shards,
                        cases=[w for i, w in enumerate(manifest['windows']) if i % args.shards == args.shard],
                        source_hashes={p.name: digest(p) for p in sources})
    (args.out / 'manifest.json').write_text(json.dumps(run_manifest, indent=2) + '\n')
    Ramulator, _ = load_backend(args.backend.resolve())
    suffix = '.dylib' if sys.platform == 'darwin' else '.so'
    library = args.backend.resolve() / 'build' / ('libneusim_ramulator_bridge' + suffix)
    identity = dict(source_manifest_sha256=digest(args.backend / 'source_manifest.json'),
        bridge_sha256=digest(library),
        memory_sha256=digest(args.backend / 'source/third_party/ramulator2' / ('libramulator' + suffix)))
    for window in run_manifest['cases']:
        config = MEMORIES[window['memory']]
        path = args.out / (window['id'] + '.yaml')
        geometry = export(config, path, mapper='MOP4CLXOR')
        width = 16 if window['memory'] == 'M-L512' else 8
        trace = args.input / window['trace']
        if digest(trace) != window['trace_sha256']:
            raise ValueError('trace differs from frozen manifest')
        if abs(geometry['peak_GBps'] - window['peak_GBps']) > 1e-9:
            raise ValueError('native bandwidth differs from frozen case')
        started = time.monotonic()
        with Ramulator(path, library=library) as memory:
            native = execute_arrays(memory, trace, channels=config['channels'], issue_width=width,
                bg_geometry=geometry['mop_geometry'] if window['bg'] else None)
            memory.finalize(args.out / (window['id'] + '_stats.yaml'))
        metrics = []
        for c in (0, 1):
            if native['stream_transactions'][c] == 0:
                continue
            actual_duration = native['last_completion_ns'][c] - native['first_offer_ns'][c]
            expected_duration = window['prediction_finish_ns'][c] - window['prediction_first_offer_ns'][c]
            if expected_duration <= 0:
                raise ValueError('nonpositive fluid reference duration')
            nbytes = native['stream_transactions'][c] * 32
            metrics.append(dict(stream='vlm' if c == 0 else 'dit',
                actual_finish_ns=native['last_completion_ns'][c], predicted_finish_ns=window['prediction_finish_ns'][c],
                actual_duration_ns=actual_duration, predicted_duration_ns=expected_duration,
                signed_error_pct=(actual_duration / expected_duration - 1) * 100,
                absolute_error_pct=abs(actual_duration / expected_duration - 1) * 100,
                actual_GBps=nbytes / actual_duration, predicted_GBps=nbytes / expected_duration))
        row = dict(window=window, native=native, metrics=metrics, backend_identity=identity,
            yaml_sha256=digest(path), wall_seconds=time.monotonic() - started,
            total_over_seq_reference=(native['logical_bytes'] / max(x for x in native['last_completion_ns'] if x is not None)
                                      / (window['eta_seq'] * geometry['peak_GBps'])))
        (args.out / (window['id'] + '.json')).write_text(json.dumps(row, indent=2) + '\n')
        print(window['id'], [round(m['signed_error_pct'], 3) for m in metrics], flush=True)
    (args.out / 'completed.json').write_text(json.dumps(dict(cases=len(run_manifest['cases']),
        manifest_sha256=digest(args.out / 'manifest.json'), backend_identity=identity), indent=2) + '\n')


if __name__ == '__main__':
    main()
