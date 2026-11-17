"""Compare default scheduling against the delivered, frozen V3 simulator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from vlasim import HWConfig, MapConfig, Simulator


def run(reference, out):
    spec = importlib.util.spec_from_file_location('vlasim._frozen_v3_sim', reference)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rows = []
    for bw in (256e9, 102.4e9, 204.8e9):
        for mode, k in (('serial', 1), ('pipelined', 1), ('pipelined', 2)):
            for launch in ('jit', 'eager'):
                def simulate(cls):
                    return cls(HWConfig(n_cores=8, dram_bw=bw),
                        MapConfig(mode=mode, dit_stages=k, vlm_cores=6,
                                  vlm_launch=launch, bw_policy='fair')).run(48, 8, record=True)
                old, new = simulate(module.Simulator), simulate(Simulator)
                del new['memory_segments']
                rows.append(dict(dram_bw=bw, mode=mode, k=k, launch=launch,
                    exact_default_output_and_timeline_match=old == new))
    result = dict(reference=str(reference), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        current_sha256=hashlib.sha256(Path('vlasim/vlasim/sim.py').read_bytes()).hexdigest(),
        scope='Analytical default-mode regression, not independent DRAM/compute validation',
        probes=rows, all_exact=all(r['exact_default_output_and_timeline_match'] for r in rows))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2)+'\n')
    if not result['all_exact']:
        raise RuntimeError('V3 default regression')
    print(f'{len(rows)} exact default output/timeline comparisons passed')


if __name__ == '__main__':
    run(Path('results/case_v3_complete/executed_sources/vlasim/sim.py'),
        Path('results/v4/validation/legacy_defaults.json'))
