"""Trace-shaped small-core DSE pilot, not a calibrated DynamicVLA hardware claim."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'vlasim'))
from v51_dse import evaluate, semantic_key, summarize
from v6_band import ScaledPeriodic
from v7_common import write_csv, write_json
from vlasim import HWConfig, MapConfig, DRAMModel
from vlasim.dynamicvla_workload import DynamicVLAWorkload, DynamicVLATiming


def run():
    p = argparse.ArgumentParser()
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cores', default='1,2,3,4,6,8')
    p.add_argument('--memories', default='LPDDR5_c4,LPDDR5_c8,LPDDR5_c16')
    p.add_argument('--sram-mb', type=float, default=32)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    profile = json.loads(a.profile.read_text())
    wl = DynamicVLAWorkload(profile)
    provider = DynamicVLATiming(ROOT/'.native/compute', wl)
    calibration = ROOT/'results/v7/inputs/calibration.json'
    cal = json.loads(calibration.read_text())
    sources = [Path(__file__), ROOT/'vlasim/vlasim/dynamicvla_workload.py',
               ROOT/'vlasim/v6_periodic.cpp', ROOT/'vlasim/v51_fast.py',
               ROOT/'vlasim/v51_dse.py', ROOT/'vlasim/v4_scheduler.py',
               ROOT/'vlasim/vlasim/sim.py', ROOT/'vlasim/v6_band.py',
               ROOT/'.native/compute/source_manifest.json']
    manifest = dict(profile_sha256=hashlib.sha256(a.profile.read_bytes()).hexdigest(),
                    calibration_sha256=hashlib.sha256(calibration.read_bytes()).hexdigest(),
                    sources={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
                    cores=a.cores, memories=a.memories, sram_mb=a.sram_mb,
                    target_precision='BF16 assumption; source mixed precision not validated after conversion',
                    memory_scope='Reused pi05-trace Ramulator fit, NOT recalibrated to DynamicVLA',
                    compute_scope='Traced GEMMs through NeuSim; conv analytical compute floor; non-matmul omitted',
                    traffic_scope='Weight-stream and prefix-KV model; uniform KV placement, approximate activation spill',
                    batching_scope='Modeled weight sharing; no real batched-policy implementation or SR validation',
                    task_episodes=0)
    mf = a.out/'manifest.json'
    if mf.exists() and json.loads(mf.read_text()) != manifest:
        raise RuntimeError('Inputs changed; select a fresh output directory')
    write_json(mf, manifest)
    lib = a.out/('periodic.dylib' if sys.platform == 'darwin' else 'periodic.so')
    subprocess.run(['c++', '-O2', '-ffp-contract=off', '-std=c++17', '-shared', '-fPIC',
                    str(ROOT/'vlasim/v6_periodic.cpp'), '-o', str(lib)], check=True)
    configurations, points, checks = [], [], []
    for memory in a.memories.split(','):
        for cores in map(int, a.cores.split(',')):
            hw = HWConfig(n_cores=cores, sram_mb=a.sram_mb, local_kb=512, slice_mode=False,
                          dram_bw=cal[memory]['geometry']['peak_GBps']*1e9)
            mappings = [('serial', cores, 1, True)]
            mappings += [('pipelined', v, k, b) for v in range(1, cores)
                         for k, b in [(1, True), (2, False), (2, True), (3, False), (3, True)]]
            for mode, split, k, batching in mappings:
                mp = MapConfig(mode=mode, vlm_cores=split, dit_stages=k, dit_batching=batching,
                               vlm_launch='periodic', launch_period_s=1)
                engine = ScaledPeriodic(hw, mp, wl, DRAMModel(**cal[memory]['params']['vla_plain']), provider, lib)
                identity = dict(memory=memory, peak_GBps=hw.dram_bw/1e9, cores=cores,
                                vlm_cores=split, mode=mode, k=k, batching=batching, sram_mb=a.sram_mb)
                if not engine.reference.sram_ok:
                    configurations.append(dict(identity, status='static_infeasible'))
                    continue
                key = semantic_key(engine)
                value = evaluate(engine, a.out/'runs'/key)
                configurations.append(dict(identity, semantic_id=key, status=value['search']['status']))
                for point in value['curve']:
                    if not point['gate']['pass_gate']:
                        continue
                    points.append(dict(identity, semantic_id=key, factor=point['factor'],
                                       L_ms=point['gate']['L_mean_s']*1000,
                                       S_ms=point['gate']['S_mean_s']*1000, **point['metrics']))
                if value['curve']:
                    point = value['curve'][0]
                    raw = engine.run(point['T_s'], 960, 192)
                    check = summarize(raw, point['T_s'], k)
                    errors = [abs(check['gate'][v]-point['gate'][v])/max(abs(point['gate'][v]), 1e-30)
                              for v in ('L_mean_s', 'S_mean_s')]
                    check_path = a.out/'runs'/key/'check960.npz'
                    np.savez_compressed(check_path, requests=np.array([[r[n] for n in
                        ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s')] for r in raw['requests']]))
                    check.update(max_relative_error=max(errors),
                                 raw_sha256=hashlib.sha256(check_path.read_bytes()).hexdigest())
                    write_json(check_path.with_suffix('.json'), check)
                    checks.append(dict(identity, semantic_id=key, pass_gate=check['gate']['pass_gate'],
                                       max_relative_error=max(errors)))
                    if not check['gate']['pass_gate'] or max(errors) > .01:
                        raise RuntimeError('960-request consistency check failed')
                print(memory, cores, mode, split, k, batching, value['search']['Tmin_s'], flush=True)
                write_csv(a.out/'configurations.csv', configurations)
                write_csv(a.out/'candidate_points.csv', points)
                write_csv(a.out/'checks960.csv', checks)
    minimum = [r for r in points if r['factor'] == 1]
    representatives = []
    for memory in a.memories.split(','):
        for cores in map(int, a.cores.split(',')):
            pool = [r for r in minimum if r['memory'] == memory and r['cores'] == cores]
            for arm in ('serial', 'no_batching', 'full'):
                eligible = [r for r in pool if arm == 'full' or r['mode'] == 'serial' or
                            (arm == 'no_batching' and (r['k'] == 1 or not r['batching']))]
                if eligible:
                    representatives.append(dict(min(eligible, key=lambda r: (r['S_ms'], r['L_ms'])), arm=arm))
    write_csv(a.out/'best_refresh.csv', representatives)
    write_json(a.out/'summary.json', dict(configurations=len(configurations), candidate_points=len(points),
               checks960=len(checks), max_check_relative_error=max(r['max_relative_error'] for r in checks),
               prefix_operations=len(wl.prefix), dit_operations_per_step=len(wl.step),
               prefix_GFLOP=wl.vlm_totals()[0]/1e9, dit_GFLOP=wl.dit_totals_per_request()[0]/1e9,
               prefix_weight_stream_GB=wl.vlm_totals()[1]/1e9,
               dit_weight_stream_GB=wl.dit_totals_per_request()[1]/1e9,
               kv_MB=wl.kv_total_bytes/1e6, activation_working_set_MB=wl.vlm_act_bytes/1e6,
               neuSim_resolved_shapes=provider.resolved_calls, analytic_conv_calls=provider.fallback_calls,
               independent_hardware_validation=False, task_episodes=0))


if __name__ == '__main__':
    run()
