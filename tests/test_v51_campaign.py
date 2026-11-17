import numpy as np
import pytest

from v51_calibration import mix_arrays
from v51_dse import evaluate,lower_bound,semantic_key
from v51_fast import Periodic,build
from vlasim import DRAMModel,HWConfig,MapConfig
from vlasim.workload import Pi05Workload


@pytest.mark.parametrize('fraction',[.25,.5,.75])
@pytest.mark.parametrize('legacy',[False,True])
def test_calibration_layout_and_counts(fraction,legacy):
    a=mix_arrays(fraction,legacy,total=65536)
    assert len(a['core'])==1024
    assert np.count_nonzero(a['core']==0)==1024*fraction
    assert np.all(a['issue_ns']==0)
    assert np.all(a['address']%64==0)
    for owner in (0,1):
        assert np.all(np.diff(a['address'][a['core']==owner])==64)
    base=2**30 if legacy else Pi05Workload().dit_layer_params*2*18
    assert a['address'][a['core']==0][0]==base


def test_periodic_semantic_identity_covers_parameters(tmp_path):
    wl=Pi05Workload();hw=HWConfig(n_cores=4);mp=MapConfig(vlm_cores=2)
    library=build(tmp_path)
    first=Periodic(hw,mp,wl,DRAMModel(),None,library)
    second=Periodic(hw,mp,wl,DRAMModel(eta_mix=.8),None,library)
    assert semantic_key(first)!=semantic_key(second)
    assert lower_bound(hw,mp,wl)>0
    assert lower_bound(hw,MapConfig(mode='serial'),wl)>0


def test_period_search_persists_every_request_and_round(tmp_path):
    wl=Pi05Workload();library=build(tmp_path)
    engine=Periodic(HWConfig(n_cores=4),MapConfig(vlm_cores=2,dit_stages=2),wl,DRAMModel(),None,library)
    result=evaluate(engine,tmp_path/'run')
    assert result['search']['Tmin_s']>0
    assert result['search']['bracket_width_s']<=.0001
    assert len(result['curve'])==5
    with np.load(tmp_path/'run/requests.npz') as raw:
        assert raw['requests'].shape[1:]==(480,4)
        assert len(raw['period_s'])==len(result['search']['trials'])+5
        assert 'curve_rounds_4' in raw.files
    assert evaluate(engine,tmp_path/'run')==result


@pytest.mark.parametrize('cores',[1,2])
def test_campaign_preserves_all_hardware_contexts(tmp_path,monkeypatch,cores):
    import v51_dse
    from v5_protocol import write_json
    from v51_package import read_csv
    monkeypatch.setattr(v51_dse,'ROOT',tmp_path)
    monkeypatch.setattr(v51_dse,'NeuSimTiming',lambda *a,**kw:None)
    params=dict(eta_seq=.9,eta_mix=.8,prio_leak=0.)
    write_json(tmp_path/'calibration.json',dict(test_memory=dict(
        params={key:params for key in ('vla_plain','vla_bg','legacy_plain','legacy_bg')},
        baseline={key:dict(params=params,scope='unit_test_fixture') for key in ('plain','bg')},
        geometry=dict(peak_GBps=100.),sampling=dict(status='unit_test_fixture'))))
    write_json(tmp_path/'heldout_gate.json',dict(status='pass',bg_main=False,dram_model_mode='unit_test_fixture'))
    root=tmp_path/'dse';build(root)
    status=v51_dse.run_shard(('test_memory',cores,str(root),'unused'))
    shard=root/f'shards/test_memory_c{cores}'
    rows=read_csv(shard/'hw_grid.csv')
    assert len({row['hardware_id'] for row in rows})==8
    assert any(row['mode']=='serial' for row in rows)
    assert status['rows']==64*(1+5*(cores-1))
    assert status['reference_rechecks']>0
    if cores>1:
        controls=read_csv(shard/'k_ablation.csv')
        assert len(controls)==80
        assert {row['dit_stages'] for row in controls}=={'1','2','3'}


def test_streaming_csv_preserves_header_union_and_pareto(tmp_path):
    from case_v3_main import write_csv
    from v51_package import concatenate,frontier,read_csv
    a=tmp_path/'a.csv';b=tmp_path/'b.csv';out=tmp_path/'all.csv'
    write_csv(a,[dict(L_s=2.,S_s=1.,first='a')])
    write_csv(b,[dict(L_s=1.,S_s=2.,second='b'),dict(L_s=3.,S_s=3.,second='c')])
    concatenate([a,b],out)
    rows=read_csv(out)
    assert rows[0]['second']=='' and rows[1]['first']==''
    assert len(rows)==3 and len(frontier(rows))==2


def test_all_pruned_pipeline_gets_explicit_k_controls(tmp_path,monkeypatch):
    import v51_ablation
    from case_v3_main import write_csv
    from v5_protocol import write_json
    from v51_package import read_csv
    monkeypatch.setattr(v51_ablation,'ROOT',tmp_path)
    monkeypatch.setattr(v51_ablation,'NeuSimTiming',lambda *a,**kw:None)
    params=dict(eta_seq=.9,eta_mix=.8,prio_leak=0.)
    write_json(tmp_path/'calibration.json',dict(test_memory=dict(
        params=dict(vla_plain=params),geometry=dict(peak_GBps=100.))))
    root=tmp_path/'dse';build(root)
    shard=root/'shards/test_memory_c2';shard.mkdir(parents=True)
    write_json(shard/'status.json',dict(unit_test_fixture=True))
    write_csv(shard/'k_ablation.csv',[dict(memory='test_memory',n_cores=2,sram_mb=8,
        local_kb=512,model='v51',bg=False,status='N/A_no_feasible_pipeline_allocation')])
    v51_ablation.supplement()
    rows=read_csv(root/'ablation_supplement/controls.csv')
    assert len(rows)==10
    assert {r['dit_stages'] for r in rows}=={'1','2','3'}
    assert all(r['status']=='bracket_found' for r in rows)
    assert all((tmp_path/r['raw']).is_file() for r in rows)
