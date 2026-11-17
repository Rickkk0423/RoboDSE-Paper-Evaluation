from dataclasses import replace

import numpy as np
import pytest

from v51_fast import Periodic, build
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.workload import Pi05Workload


@pytest.fixture(scope='module')
def kernel(tmp_path_factory):
    return build(tmp_path_factory.mktemp('periodic_kernel'))


@pytest.mark.parametrize('k',[0,1,2,3])
@pytest.mark.parametrize('policy',['fair','vlm_priority','bg'])
@pytest.mark.parametrize('period',[.03,.2,.8])
@pytest.mark.parametrize('sram',[8,64])
def test_periodic_kernel_matches_reference_every_request_and_round(kernel,k,policy,period,sram):
    hw=HWConfig(n_cores=4,dram_bw=100e9,sram_mb=sram)
    mp=MapConfig(mode='serial' if k==0 else 'pipelined',vlm_cores=2,dit_stages=max(1,k),
        bw_policy='fair' if policy=='bg' else policy,stream_partition=.5 if policy=='bg' else None,
        vlm_launch='periodic',launch_period_s=period,dit_batching=not(k==3))
    wl=Pi05Workload()
    dram=DRAMModel(eta_seq=.91,eta_mix=.77)
    reference=Simulator(hw,mp,wl,dram).run(24,4,diagnostics=True)
    accelerated=Periodic(hw,mp,wl,dram,None,kernel).run(period,24,4)
    for a,b in zip(reference['requests'],accelerated['requests']):
        assert a.keys()==b.keys()
        for key in a:
            if a[key] is None or isinstance(a[key],bool):
                assert a[key]==b[key]
            else:
                assert a[key]==pytest.approx(b[key],rel=1e-12,abs=1e-10),key
    assert len(reference['dit_rounds'])==len(accelerated['dit_rounds'])
    for a,b in zip(reference['dit_rounds'],accelerated['dit_rounds']):
        for key in b.keys()-{'stage_mask'}:
            assert a[key]==pytest.approx(b[key],rel=1e-12,abs=1e-10),key
    for key in ('vlm_busy','dit_busy','makespan_s','dit_GB_per_req','dram_GB_per_req'):
        assert reference[key]==pytest.approx(accelerated[key],rel=1e-12,abs=1e-10),key
    assert reference['vlm_queue']['steady_max_length']==accelerated['vlm_queue']['steady_max_length']


@pytest.mark.parametrize('sram',[8,64])
def test_unbatched_k2_long_sequence_matches_original_scheduler(kernel,sram):
    hw=HWConfig(n_cores=4,dram_bw=100e9,sram_mb=sram)
    mp=MapConfig(vlm_cores=2,dit_stages=2,dit_batching=False,
        vlm_launch='periodic',launch_period_s=.12)
    wl=Pi05Workload();dram=DRAMModel(eta_seq=.91,eta_mix=.77)
    reference=Simulator(hw,mp,wl,dram).run(480,96,diagnostics=True)
    accelerated=Periodic(hw,mp,wl,dram,None,kernel).run(.12,480,96)
    for a,b in zip(reference['requests'],accelerated['requests']):
        for key in ('obs_s','vlm_start_s','vlm_end_s','done_s'):
            assert a[key]==pytest.approx(b[key],rel=1e-12,abs=1e-10)
    assert len(reference['dit_rounds'])==len(accelerated['dit_rounds'])
    for a,b in zip(reference['dit_rounds'],accelerated['dit_rounds']):
        for key in ('duration_s','compute_s','exposed_memory_s','dram_bytes','weight_bytes'):
            assert a[key]==pytest.approx(b[key],rel=1e-12,abs=1e-10)
