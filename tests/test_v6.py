from dataclasses import replace

import numpy as np
import pytest

from v6_band import ScaledPeriodic,build,parse
from v51_fast import Periodic,build as old_build
from vlasim import HWConfig,MapConfig,DRAMModel
from vlasim.workload import Pi05Workload


@pytest.mark.parametrize('mode,k,batching',[('serial',1,True),('pipelined',1,True),
    ('pipelined',2,True),('pipelined',3,True),('pipelined',2,False),('pipelined',3,False)])
def test_v6_band_identity_preserves_v51(tmp_path,monkeypatch,mode,k,batching):
    import v6_band
    monkeypatch.setattr(v6_band,'ROOT',tmp_path)
    wl=Pi05Workload();hw=HWConfig(n_cores=4)
    mp=MapConfig(mode=mode,vlm_cores=2,dit_stages=k,dit_batching=batching)
    dram=DRAMModel()
    original=Periodic(hw,mp,wl,dram,None,old_build(tmp_path/'original')).run(.25,120)
    scaled=ScaledPeriodic(hw,mp,wl,dram,None,build()).run(.25,120)
    assert np.allclose([r['done_s'] for r in original['requests']],
        [r['done_s'] for r in scaled['requests']],rtol=0,atol=1e-8)
    assert scaled['dram_GB_per_req']==pytest.approx(original['dram_GB_per_req'],rel=1e-10)


def test_band_row_parser_types():
    hw=parse(dict(n_cores='4',slice_mode='False',local_kb='512'),HWConfig)
    assert hw.n_cores==4 and isinstance(hw.n_cores,int) and hw.slice_mode is False
    mp=parse(dict(mode='serial',dit_batching='False',launch_period_s='0.1'),MapConfig)
    assert mp.mode=='serial' and mp.dit_batching is False and mp.launch_period_s==.1


def test_frontend_share_matches_proportional_issue_and_redistributes():
    from v6_arbiter import FrontendProportional
    model=FrontendProportional(eta_seq=1.,eta_mix=1.,issue_weights={'vlm':1.,'dit':3.})
    assert model.allocate(100.,{'vlm':100.,'dit':100.})=={'vlm':25.,'dit':75.}
    assert model.allocate(100.,{'vlm':10.,'dit':100.})=={'vlm':10.,'dit':90.}
    assert model.allocate(100.,{'vlm':0.,'dit':100.})=={'vlm':0.,'dit':100.}


def test_frontend_prediction_equalizes_completion_not_bytes():
    from v6_arbiter import frontend_prediction
    prediction=frontend_prediction(dict(bytes_by_stream=[100,300],peak_GBps=1.,params=dict(eta_seq=1.)),1.)
    assert prediction==pytest.approx([400.,400.])
