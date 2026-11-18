"""Resource-first small-array exploration; preserve the original pilot artifacts."""
import argparse
from dataclasses import asdict
import hashlib
import itertools
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
from vlasim import HWConfig, MapConfig, DRAMModel, Simulator
from vlasim.dynamicvla_workload import DynamicVLATiming
from vlasim.model_registry import load_workload


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mappings(cores):
    return [('serial', cores, 1, True)] + [
        ('pipelined', split, k, batch) for split in range(1, cores)
        for k, batch in ((1, True), (2, False), (2, True), (3, False), (3, True))]


def make_hardware(dim, cores, sram, bandwidth):
    if dim not in (16, 32, 64) or cores < 1 or sram <= 0 or bandwidth <= 0:
        raise ValueError('Invalid small-array hardware configuration')
    return HWConfig(n_cores=cores, array_rows=dim, array_cols=dim, freq_hz=1e9,
                    sram_mb=sram, local_kb=32, slice_mode=False, dram_bw=bandwidth*1e9)


def run():
    p = argparse.ArgumentParser()
    p.add_argument('--profile', type=Path, default=ROOT/'publication/dynamicvla_pilot/profile.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--arrays', default='16,32,64')
    p.add_argument('--cores', default='1,2,4')
    p.add_argument('--srams', default='4,8,32')
    p.add_argument('--bandwidths', default='12.8,25.6,51.2')
    p.add_argument('--calibration', type=Path,
                   help='DynamicVLA-specific DRAM calibration JSON. If omitted, use the frozen Pi0.5 anchor.')
    a = p.parse_args()
    grid = dict(arrays=list(map(int, a.arrays.split(','))), cores=list(map(int, a.cores.split(','))),
                srams=list(map(float, a.srams.split(','))), bandwidths=list(map(float, a.bandwidths.split(','))))
    for dim, cores, sram, bw in itertools.product(*grid.values()):
        make_hardware(dim, cores, sram, bw)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.calibration:
        cal_path = a.calibration.resolve()
        cal = json.loads(cal_path.read_text())
        cal_params = cal['params']
        memory_scope = 'dynamicvla_native_ramulator'
    else:
        cal_path = ROOT/'results/v7/inputs/calibration.json'
        cal = json.loads(cal_path.read_text())['LPDDR5_c4']
        cal_params = cal['params']['vla_plain']
        memory_scope = 'inherited_fit_anchor'
    sources = [Path(__file__), ROOT/'vlasim/vlasim/dynamicvla_workload.py',
               ROOT/'vlasim/vlasim/neusim_compute.py', ROOT/'vlasim/vlasim/hw.py',
               ROOT/'vlasim/vlasim/sim.py', ROOT/'vlasim/v6_periodic.cpp',
               ROOT/'vlasim/v51_fast.py', ROOT/'vlasim/v6_band.py', ROOT/'vlasim/v51_dse.py',
               ROOT/'vlasim/v4_scheduler.py', ROOT/'.native/compute/source_manifest.json']
    manifest = dict(grid=grid, profile_sha256=digest(a.profile), calibration_sha256=digest(cal_path),
                    calibration_source=str(cal_path),
                    sources={str(f.relative_to(ROOT)): digest(f) for f in sources},
                    freq_GHz=1, local_kb=32, weight_precision='BF16 target assumption',
                    memory_model=('DynamicVLA-native eta_seq/eta_mix are used when --calibration is supplied. '
                    '12.8/25.6/51.2 GB/s remain peak-bandwidth sensitivity points unless their geometry is '
                    'covered by the native calibration. '
                    f'calibration_model={cal.get("model", "pi05")}; calibration_scope={memory_scope}'),
                    compute_model='NeuSim GEMMs; analytical conv floor; non-matmul work omitted',
                    sram_scope='32KB private passes static tile feasibility; no local-capacity timing model. '
                    'Shared activation and KV storage use the exploratory trace adapter.',
                    selection='Resource vectors under timing bounds, not latency minimization or task SR',
                    task_episodes=0, new_gpu_runs=0, new_ramulator_runs=0)
    path = a.out/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise RuntimeError('Manifest mismatch; choose a new output directory')
    write_json(path, manifest)
    library = a.out/('periodic.dylib' if sys.platform == 'darwin' else 'periodic.so')
    subprocess.run(['c++', '-O2', '-ffp-contract=off', '-std=c++17', '-shared', '-fPIC',
                    str(ROOT/'vlasim/v6_periodic.cpp'), '-o', str(library)], check=True)
    wl = load_workload('dynamicvla', profile=a.profile)
    provider = DynamicVLATiming(ROOT/'.native/compute', wl)
    dram = DRAMModel(**{k: cal_params[k] for k in ('eta_seq', 'eta_mix', 'prio_leak')
                        if cal_params.get(k) is not None})
    configs, points, checks, reference_checks = [], [], [], []
    rechecked = {}
    for dim, cores, sram, bw in itertools.product(*grid.values()):
        hw = make_hardware(dim, cores, sram, bw)
        for mode, split, k, batch in mappings(cores):
            mp = MapConfig(mode=mode, vlm_cores=split, dit_stages=k, dit_batching=batch,
                           vlm_launch='periodic', launch_period_s=1)
            engine = ScaledPeriodic(hw, mp, wl, dram, provider, library)
            identity = dict(array_dim=dim, cores=cores, total_MACs=dim*dim*cores,
                            peak_TFLOPs=hw.peak/1e12, freq_GHz=1, local_kb=32,
                            sram_mb=sram, peak_GBps=bw, mode=mode, vlm_cores=split, k=k,
                            batching=batch, memory_scope=memory_scope if a.calibration or bw == 51.2
                            else 'uncalibrated_peak_sensitivity')
            if not engine.reference.sram_ok:
                configs.append(dict(identity, status='static_infeasible'))
                continue
            key = semantic_key(engine)
            folder = a.out/'runs'/key
            value = evaluate(engine, folder)
            configs.append(dict(identity, semantic_id=key, status=value['search']['status']))
            if value['curve']:
                first = value['curve'][0]
                if key not in rechecked:
                    result = engine.run(first['T_s'], 960, 192)
                    check = summarize(result, first['T_s'], k)
                    error = max(abs(check['gate'][n]-first['gate'][n])/max(abs(first['gate'][n]), 1e-30)
                                for n in ('L_mean_s', 'S_mean_s'))
                    raw_path = folder/'check960.npz'
                    np.savez_compressed(raw_path, requests=np.array([[r[n] for n in
                        ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s')] for r in result['requests']]))
                    check.update(max_relative_error=error, raw_sha256=digest(raw_path))
                    write_json(raw_path.with_suffix('.json'), check)
                    rechecked[key] = check
                check = rechecked[key]
                if not check['gate']['pass_gate'] or check['max_relative_error'] > .01:
                    raise RuntimeError('960-request check failed')
                checks.append(dict(identity, semantic_id=key, max_relative_error=check['max_relative_error'], passed=True))
                # Exercise every array dimension and execution organization against Python.
                refkey = (dim, mode, k, batch)
                if refkey not in {tuple(r['key']) for r in reference_checks}:
                    period = first['T_s']
                    mp.launch_period_s = period
                    ref = Simulator(hw, mp, wl, dram, provider).run(24, 6, diagnostics=True)
                    fast = engine.run(period, 24, 6)
                    errors = [abs(x[n]-y[n]) for x, y in zip(ref['requests'], fast['requests'], strict=True)
                              for n in ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s')]
                    errors.extend(abs(ref[n]-fast[n]) for n in ('dram_GB_per_req', 'dit_GB_per_req'))
                    if max(errors) > 1e-8:
                        raise RuntimeError('Small-array Python/C++ mismatch')
                    reference_checks.append(dict(key=refkey, hardware=asdict(hw), max_abs_error=max(errors)))
            for point in value['curve']:
                if not point['gate']['pass_gate']:
                    continue
                s = point['gate']['S_mean_s']
                useful = sum((wl.vlm_totals()[0], wl.dit_totals_per_request()[0]))/(hw.peak*s)
                if useful > 1.0001:
                    raise RuntimeError('Useful throughput exceeds physical compute peak')
                points.append(dict(identity, semantic_id=key, factor=point['factor'],
                                   L_ms=point['gate']['L_mean_s']*1000, S_ms=s*1000,
                                   useful_throughput_fraction=useful, **point['metrics']))
        write_csv(a.out/'configurations.csv', configs)
        write_csv(a.out/'candidate_points.csv', points)
        write_csv(a.out/'checks960.csv', checks)
        write_json(a.out/'reference_checks.json', reference_checks)
        print('hardware', dim, cores, sram, bw, 'configurations', len(configs), flush=True)
    write_json(a.out/'summary.json', dict(hardware_identities=len(list(itertools.product(*grid.values()))),
               configurations=len(configs), candidate_points=len(points), checks960=len(checks),
               unique_960_runs=len(rechecked), python_cpp_checks=len(reference_checks),
               max_relative_error=max(r['max_relative_error'] for r in checks),
               max_python_cpp_abs_error=max(r['max_abs_error'] for r in reference_checks),
               target_latency_ms=[100, 300], target_is_exploratory=True,
               new_gpu_runs=0, new_ramulator_runs=8 if a.calibration else 0, task_episodes=0,
               calibration_model=cal.get('model', 'pi05'), calibration_scope=memory_scope,
               calibration_sha256=digest(cal_path)))


if __name__ == '__main__':
    run()
