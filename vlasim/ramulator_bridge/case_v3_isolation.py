"""Freeze and execute isolation controls on the calibrated MOP4CLXOR mapping."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from case_v3_p0 import MEMORIES, digest, export
from channel_frontend import VERSION, execute
from run_native import load_backend


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--backend', type=Path, required=True)
    ap.add_argument('--traces', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--collect-only', action='store_true', help='recover summary from completed immutable raw runs')
    args = ap.parse_args()
    if args.collect_only:
        collect(args)
        return
    args.out.mkdir(parents=True, exist_ok=False)
    cases = []
    for name in MEMORIES:
        cases.extend(dict(memory=name, trace=f'seq_{size}KB', partition=None, bg=False)
                     for size in (4, 64, 1024))
        for fraction, bg in ((None, False), (.5, False), (.625, False), (.75, False), (None, True)):
            cases.extend(dict(memory=name, trace=f'mix_{ratio}', partition=fraction, bg=bg)
                         for ratio in (25, 50, 75))
    sources = [Path(__file__), Path(__file__).with_name('channel_frontend.py'),
               Path(__file__).with_name('case_v3_p0.py'), Path(__file__).with_name('run_native.py')]
    frozen = args.out / 'executed_sources'
    frozen.mkdir()
    for source in sources:
        shutil.copy2(source, frozen / source.name)
    manifest = dict(cases=cases, source_hashes={p.name: digest(p) for p in sources},
                    traces={p.name: digest(p) for p in args.traces.glob('*.csv')},
                    protocol='MOP4CLXOR; FRFCFS/Open; outstanding512; issue8 except L512 issue16. Fixed I1 requires all three ratios >=95% median sequential reference. I2 is shared channels and is never treated as an I1 cap model.')
    (args.out / 'experiment_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    Ramulator, _ = load_backend(args.backend.resolve())
    suffix = '.dylib' if sys.platform == 'darwin' else '.so'
    library = args.backend.resolve() / 'build' / ('libneusim_ramulator_bridge' + suffix)
    rows = []
    for i, case in enumerate(cases):
        config = MEMORIES[case['memory']]
        path = args.out / f'run_{i:03d}.yaml'
        geometry = export(config, path, mapper='MOP4CLXOR')
        width = 16 if case['memory'] == 'M-L512' else 8
        trace = args.traces / (case['trace'] + '.csv')
        with Ramulator(path, library=library) as memory:
            native = execute(memory, trace, channels=config['channels'], issue_width=width,
                             partition=case['partition'],
                             mop_geometry=geometry['mop_geometry'] if case['bg'] else None)
            memory.finalize(args.out / f'run_{i:03d}_stats.yaml')
        row = dict(case, native=native, geometry=geometry, issue_width=width,
                   trace_sha256=digest(trace), yaml_sha256=digest(path))
        rows.append(row)
        (args.out / f'run_{i:03d}.json').write_text(json.dumps(row, indent=2) + '\n')
        print(i, case, native['achieved_GBps'], flush=True)
    collect(args)


def collect(args):
    rows = [json.loads(p.read_text()) for p in sorted(args.out.glob('run_*.json'))]
    manifest = json.loads((args.out / 'experiment_manifest.json').read_text())
    if len(rows) != len(manifest['cases']):
        raise ValueError('incomplete native isolation set')
    for i, row in enumerate(rows):
        if any(row[k] != manifest['cases'][i][k] for k in manifest['cases'][i]):
            raise ValueError('case identity differs from frozen manifest')
        if digest(args.out / f'run_{i:03d}.yaml') != row['yaml_sha256']:
            raise ValueError('configuration hash mismatch')
        native = row['native']
        if native['accepted'] != native['completed'] or native['logical_bytes'] != 4 * 1024**2:
            raise ValueError('native transaction accounting failure')
    summary = {}
    for name in MEMORIES:
        subset = [r for r in rows if r['memory'] == name]
        seq = sorted(r['native']['achieved_GBps'] for r in subset if r['trace'].startswith('seq'))
        reference = seq[1]
        mixed = [r for r in subset if r['trace'] == 'mix_50' and r['partition'] is None and not r['bg']][0]
        peak = mixed['geometry']['peak_GBps']
        supported = [p for p in (.5, .625, .75) if all(
            r['native']['achieved_GBps'] >= .95 * reference for r in subset if r['partition'] == p)]
        summary[name] = dict(peak_GBps=peak, seq_GBps=seq, eta_seq=reference / peak,
                             eta_mix=mixed['native']['achieved_GBps'] / reference,
                             supported_channel_partitions=supported,
                             bg_all_ratios_pass=all(r['native']['achieved_GBps'] >= .95 * reference
                                                   for r in subset if r['bg']))
    suffix = '.dylib' if sys.platform == 'darwin' else '.so'
    library = args.backend.resolve() / 'build' / ('libneusim_ramulator_bridge' + suffix)
    identity = dict(source_manifest_sha256=digest(args.backend / 'source_manifest.json'),
                    bridge_sha256=digest(library),
                    memory_sha256=digest(args.backend / 'source/third_party/ramulator2' / ('libramulator' + suffix)))
    (args.out / 'isolation_report.json').write_text(json.dumps(dict(memories=summary, runs=rows,
        backend_identity=identity, manifest_sha256=digest(args.out / 'experiment_manifest.json'),
        collector_sha256=digest(Path(__file__)), frontend_version=VERSION), indent=2) + '\n')


if __name__ == '__main__':
    main()
