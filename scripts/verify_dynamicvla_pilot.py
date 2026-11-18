"""Independent Python/C++ scheduler comparison and pilot evidence hash checks."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'vlasim'))
from v6_band import ScaledPeriodic
from v7_common import write_json
from vlasim import Simulator, HWConfig, MapConfig, DRAMModel
from vlasim.dynamicvla_workload import DynamicVLAWorkload, DynamicVLATiming


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args()
    profile = a.root/'profile_complete/profile.json'
    wl = DynamicVLAWorkload(json.loads(profile.read_text()))
    provider = DynamicVLATiming(ROOT/'.native/compute', wl)
    calibration = ROOT/'results/v7/inputs/calibration.json'
    cal = json.loads(calibration.read_text())['LPDDR5_c4']
    hw = HWConfig(n_cores=4, sram_mb=32, local_kb=512, slice_mode=False,
                  dram_bw=cal['geometry']['peak_GBps']*1e9)
    dram = DRAMModel(**cal['params']['vla_plain'])
    lib = a.root/'dse'/('periodic.dylib' if sys.platform == 'darwin' else 'periodic.so')
    comparisons = []
    for mode, k, batching, period in [('serial', 1, True, .061),
                                     ('pipelined', 1, True, .061),
                                     ('pipelined', 2, True, .041),
                                     ('pipelined', 3, True, .037),
                                     ('pipelined', 2, False, .061),
                                     ('pipelined', 3, False, .061)]:
        mp = MapConfig(mode=mode, vlm_cores=2, dit_stages=k, dit_batching=batching,
                       vlm_launch='periodic', launch_period_s=period)
        engine = ScaledPeriodic(hw, mp, wl, dram, provider, lib)
        fast = engine.run(period, 24, 6)
        reference = Simulator(hw, mp, wl, dram, provider).run(24, 6, diagnostics=True)
        errors = []
        for left, right in zip(fast['requests'], reference['requests'], strict=True):
            for key in ('obs_s', 'vlm_start_s', 'vlm_end_s', 'done_s'):
                errors.append(abs(left[key]-right[key]))
        for key in ('dram_GB_per_req', 'dit_GB_per_req', 'makespan_s'):
            errors.append(abs(fast[key]-reference[key]))
        if max(errors) > 1e-8:
            raise RuntimeError('Python/C++ disagreement: '+str(max(errors)))
        comparisons.append(dict(mode=mode, k=k, batching=batching, max_abs_error=max(errors), requests=24))
    checked = 0
    for directory in ('dse', 'dse_sram8', 'dse_sram64'):
        folder = a.root/directory
        manifest = json.loads((folder/'manifest.json').read_text())
        assert manifest['profile_sha256'] == digest(profile)
        assert manifest['calibration_sha256'] == digest(calibration)
        for name, sha in manifest['sources'].items():
            assert digest(ROOT/name) == sha, name
        for status in (folder/'runs').glob('*/status.json'):
            saved = json.loads(status.read_text())
            assert digest(status.parent/'requests.npz') == saved['raw_sha256']
            check = json.loads((status.parent/'check960.json').read_text())
            assert digest(status.parent/'check960.npz') == check['raw_sha256']
            assert check['gate']['pass_gate'] and check['max_relative_error'] <= .01
            checked += 1
    result = dict(passed=True, python_cpp_comparisons=comparisons,
                  verified_run_directories=checked, physical_validation=False, task_episodes=0)
    write_json(a.root/'verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
