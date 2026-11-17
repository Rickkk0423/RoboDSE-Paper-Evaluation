"""Check periodic semantics on the exact eight frozen P0-A model configurations."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import shutil

from v4_scheduler import collect, digest, run_item, write_json


def main():
    inputs = Path('results/v4/p0a_input/manifest.json')
    out = Path('results/v4/p0b_replay_configs')
    snapshot = Path('.native/compute').resolve()
    manifest = json.loads(inputs.read_text())
    items = [dict(config_id=c['config_id'], config=c['config'], jit_diagnostic=False,
        task=dict(track='neusim_unsliced_hybrid', calibration=c['calibration']),
        replay_case=c['name'], initial_period_s=.1) for c in manifest['cases']]
    out.mkdir(parents=True, exist_ok=False)
    source_root = Path(__file__).resolve().parent
    sources = [Path(__file__), source_root/'v4_scheduler.py', source_root/'case_v3_main.py',
        source_root/'compute_diagnostics.py', *sorted((source_root/'vlasim').glob('*.py'))]
    hashes = {}
    for source in sources:
        relative = source.resolve().relative_to(source_root)
        target = out/'executed_sources'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[str(relative)] = digest(source)
    write_json(out/'experiment_manifest.json', dict(items=items,
        p0a_input_manifest_sha256=digest(inputs), source_hashes=hashes,
        snapshot_manifest_sha256=digest(snapshot/'source_manifest.json'),
        scope='Exact P0-A configuration scheduler-only supplement; BG model calibration '
              'is retained as an unvalidated scenario, not promoted to native validation.',
        periodic_requests=[480, 960], warmup=[96, 192], search_resolution_s=.0001,
        factors=[1, 1.1, 1.25, 1.5, 2], strict_tolerance_s=1e-9))
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(run_item, item, str(out.resolve()), str(snapshot), 1920, 10.) for item in items]
        for future in as_completed(pending):
            result = future.result()
            print(result['config_id'][:12], result['all_curve_confirmed'], flush=True)
    result = collect(out)
    print(json.dumps({k: v for k, v in result.items() if k != 'artifact_sha256'}), flush=True)


if __name__ == '__main__':
    main()
