"""Cross-host reproducibility for selected unsliced NeuSim Case v3 mappings."""
import argparse
import json
from pathlib import Path

from case_v3_main import digest, write_json
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepare', type=Path)
    ap.add_argument('--input', type=Path)
    ap.add_argument('--snapshot', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.prepare:
        manifest = json.loads((args.prepare / 'experiment_manifest.json').read_text())
        records = json.loads((args.prepare / 'compute_report.json').read_text())['hybrid_results']
        tasks = {t['id']: t for t in manifest['tasks']}
        records = [r for r in records if r['extraction_reason'] != 'regression']
        write_json(args.out, dict(snapshot_sha256=manifest['compute_snapshot_sha256'],
            source_hashes=manifest['source_hashes'],
            cases=[dict(config=r['config'], calibration=tasks[r['task']]['calibration'], config_id=r['config_id'],
                expected={k:float(r[k]) for k in ('S_mean_ms', 'L_mean_ms', 'dit_GB_per_req', 'dram_GB_per_req', 'dit_busy', 'vlm_busy')}) for r in records]))
        return
    data = json.loads(args.input.read_text())
    if digest(args.snapshot / 'source_manifest.json') != data['snapshot_sha256']:
        raise ValueError('compute snapshot differs across hosts')
    for name, expected in data['source_hashes'].items():
        if digest(Path(__file__).parent / name) != expected:
            raise ValueError('executed code differs across hosts: ' + name)
    wl = Pi05Workload()
    provider = NeuSimTiming(args.snapshot, wl, allow_analytical_siglip=True)
    rows = []
    for case in data['cases']:
        cfg = case['config']
        result = Simulator(HWConfig(**cfg['hardware']), MapConfig(**cfg['mapping']), wl=wl,
            dram=DRAMModel(**case['calibration']['params']), compute_time_fn=provider).run(120, 24)
        measured = dict(S_mean_ms=result['S_mean'] * 1000, L_mean_ms=result['L_mean'] * 1000,
                       **{k:result[k] for k in ('dit_GB_per_req', 'dram_GB_per_req', 'dit_busy', 'vlm_busy')})
        errors = {k: abs(measured[k] - v) for k, v in case['expected'].items()}
        if max(errors.values()) > 1e-8:
            raise ValueError('cross-host result mismatch: ' + str(errors))
        rows.append(dict(config_id=case['config_id'], actual=measured, absolute_errors=errors))
    write_json(args.out, dict(input_sha256=digest(args.input), source_sha256=digest(Path(__file__)),
        snapshot_sha256=data['snapshot_sha256'], reproduced=len(rows), tolerance=1e-8, results=rows))
    print('reproduced', len(rows))


if __name__ == '__main__':
    main()
