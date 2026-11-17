"""Sampling controls only, not heldout validation or authorization for V5 DSE."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import yaml

from case_v3_p0 import MEMORIES, digest, export
from run_native import load_backend
from v5_native import build, execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for name in ('v5_sampling_diagnostic.py', 'v5_driver.cpp', 'v5_native.py'):
        shutil.copy2(Path(__file__).with_name(name), args.out / name)
    Ramulator, _ = load_backend(args.backend.resolve())
    library = args.backend.resolve() / 'build' / (
        'libneusim_ramulator_bridge' + ('.dylib' if sys.platform == 'darwin' else '.so'))
    driver = build(args.out)
    geometry = export(MEMORIES['M-L256'], args.out / 'dram.yaml', mapper='MOP4CLXOR')
    controls = [('contiguous', 2048, 1), ('line_stride_v4', 64, 10),
                ('block_2KB_v5', 2048, 10), ('channel_row_span_diagnostic', 32768, 10),
                ('all_bank_row_span_diagnostic', 524288, 10)]
    manifest = dict(controls=controls, sampled_bytes_per_control=64 * 1024**2,
                    scope='Synthetic all-read serial controls; larger spans are diagnostics only, '
                          'not the specified 2KB or single physical-row W5 acceptance.',
                    geometry=geometry, driver_source_sha256=digest(args.out / 'v5_driver.cpp'))
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    rows = []
    for label, block, stride in controls:
        blocks = 64 * 1024**2 // block
        addresses = (np.arange(blocks, dtype=np.uint64)[:, None] * block * stride
                     + np.arange(0, block, 64, dtype=np.uint64)).ravel()
        core = np.zeros(len(addresses), dtype=np.uint8)
        core[len(addresses) // 2:] = 1
        trace = args.out / (label + '.npz')
        np.savez_compressed(trace, issue_ns=np.zeros(len(addresses)), core=core,
                            address=addresses, write=np.zeros(len(addresses), dtype=np.uint8),
                            epoch=core.astype(np.uint32))
        with Ramulator(args.out / 'dram.yaml', library=library) as memory:
            native = execute(memory, trace, channels=16, issue_width=8,
                             driver=driver, library=library)
            stats = args.out / (label + '_stats.yaml')
            memory.finalize(stats)
        raw = yaml.safe_load(stats.read_text())['memory_system']
        reads = raw['total_num_read_requests']
        served = sum(c.get('num_read_reqs_served', 0) + c.get('num_read_reqs_forwarded', 0)
                     for c in raw['controller'])
        if reads != native['completed'] or reads != served or raw['total_num_write_requests']:
            raise RuntimeError('HARD_STOP_native_accounting_mismatch')
        end = max(native['last_completion_ns'])
        row = dict(label=label, block_bytes=block, stride=stride, native=native,
                   achieved_GBps=native['logical_bytes'] / end,
                   eta_peak=native['logical_bytes'] / end / geometry['peak_GBps'],
                   trace_sha256=digest(trace), accounting_ok=True)
        rows.append(row)
        (args.out / (label + '.json')).write_text(json.dumps(row, indent=2) + '\n')
        print(label, row['eta_peak'], flush=True)
    (args.out / 'completed.json').write_text(json.dumps(dict(results=rows), indent=2) + '\n')


if __name__ == '__main__':
    main()
