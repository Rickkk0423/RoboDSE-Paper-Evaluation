"""Materialize the requested, unexecuted Stage B grid and pinned capability evidence."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(backend, out):
    root = backend / 'source/third_party/ramulator2'
    gddr = root / 'python/ramulator/dram/gddr6.py'
    mapper = root / 'src/ramulator/memory_system/channel_mapper/impl/cache_line_interleave.cpp'
    tree = ast.parse(gddr.read_text())
    timings = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                and t.value.id == 'GDDR6' and t.attr == 'timing_presets' for t in n.targets))
    rates = sorted({t['rate'] for t in timings.values()})
    caps = dict(scope='Pinned local source audit, not native calibration or timing validation',
        source_manifest_sha256=digest(backend / 'source_manifest.json'),
        source_files={str(p.relative_to(backend)): digest(p) for p in (gddr, mapper)},
        power_of_two_channel_guard='power-of-two channel count' in mapper.read_text(),
        blocked_channel_counts=[12, 24], gddr6_rate_presets_Mbps=rates,
        gddr6_timing_preset_names=list(timings),
        requested_missing_rates_Mbps=[r for r in (16000, 20000) if r not in rates],
        gddr6x_module_paths=[str(p.relative_to(root)) for p in root.rglob('*gddr6x*')],
        policy='Do not modify pinned sources or rescale unspecified timings. '
               '960GB/s GDDR6 would remain a proxy, not GDDR6X PAM4 validation.')
    memories = [dict(memory=f'LPDDR5_{ch}ch', channels=ch, peak_GBps=12.8*ch,
        blockers=['non_power_of_two_channel_mapper'] if ch in (12, 24) else [])
        for ch in (4, 8, 12, 16, 24, 32)]
    memories += [dict(memory=f'GDDR6_{bw}', channels=None, peak_GBps=bw,
        blockers=['missing_rate_preset', 'mapper_efficiency_not_measured'])
        for bw in (512, 768, 960)]
    memories += [dict(memory='HBM2_8ch', channels=8, peak_GBps=256, blockers=[])]
    rows = []
    for cores in (1, 2, 3, 4, 6, 8, 12, 16):
        mappings = [('serial', cores, 1)] + [('pipelined', split, k)
            for split in range(1, cores) for k in (1, 2, 3)]
        for memory in memories:
            for shared in (8, 16, 32, 64):
                for private in (.5, 2):
                    for mode, vlm, k in mappings:
                        cfg = dict(cores=cores, memory=memory['memory'],
                            nominal_peak_GBps=memory['peak_GBps'], shared_SRAM_MB=shared,
                            private_SRAM_MB=private, mode=mode, vlm_cores=vlm, k=k,
                            placement='plain', policy='fair', launch='periodic')
                        cid = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
                        rows.append(dict(config_id=cid, **cfg,
                            status='planned_not_executed_stage_A_gate',
                            capability_blockers=';'.join(memory['blockers']),
                            SRAM_pruning='not_evaluated', lower_bound_pruning='not_evaluated',
                            calibration='not_measured', Tmin_s=None, L_curve=None))
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'hardware_grid_plan.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / 'backend_capabilities.json').write_text(json.dumps(caps, indent=2)+'\n')
    plan = dict(stage='B', status='held_until_stage_A_passes', executed_simulations=0,
        planned_hardware_points=640, planned_plain_mapping_rows=len(rows),
        planned_curve_factors=[1, 1.1, 1.25, 1.5, 2],
        bg='not expanded: requires P0-A dynamic validation',
        calibration_plan=dict(lpddr5_measured_channels=[4, 16, 32],
            lpddr5_interpolated_channels=[8, 12, 24], lpddr5_holdout_channels=[8, 24],
            gddr6_measured_GBps=[512, 960], gddr6_holdout_GBps=[768],
            holdout_max_relative_error=.05, gddr6_mapper_min_seq_efficiency=.8),
        costs=dict(status='placeholder_not_calibrated', lpddr5_area=None,
            lpddr5_energy=None, gddr6_area=None, gddr6_energy=None,
            hbm2_area=None, hbm2_energy=None),
        not_produced=['hw_grid.csv', 'frontier.csv', 'V4 measured DRAM calibrations'],
        reason='No numeric sweep, pruning claims, calibration, or ranking before Stage A gate.')
    (out / 'stage_b_plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--backend', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(build(args.backend, args.out), indent=2))
