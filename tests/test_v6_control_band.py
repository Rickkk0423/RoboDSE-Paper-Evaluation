from types import SimpleNamespace

import numpy as np

from v6_common import write_csv,write_json
from v51_package import read_csv


def test_blank_config_ids_do_not_alias_control_k(tmp_path,monkeypatch):
    import v6_control_band as module
    monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.setattr(module,'OLD',tmp_path/'old')
    (tmp_path/'band').mkdir()
    rows=[dict(memory='LPDDR5_c8',n_cores=4,hardware_id='fixture',config_id='',model='v51',
        track='neusim_unsliced',bw_policy='fair',bg='False',mode='pipelined',dit_stages=k,
        dit_batching=True,band_role='same_allocation_control',period_s=1.) for k in (1,2,3)]
    write_csv(tmp_path/'band/inputs.csv',rows)
    write_json(tmp_path/'old/calibration.json',dict(LPDDR5_c8=dict(config=dict(standard='LPDDR5'))))
    write_json(tmp_path/'band/quantiles.json',dict(groups={'LPDDR5/W1/vlm':dict(p5=0.,p50=0.,p95=0.)}))
    def engine(row,*args,**kwargs):
        k=int(row['dit_stages'])
        return SimpleNamespace(k=k,run=lambda period:dict(requests=[dict(obs_s=float(i),vlm_start_s=float(i),
            vlm_end_s=i+.5,done_s=float(i+k)) for i in range(480)]))
    monkeypatch.setattr(module,'engine_from_row',engine)
    monkeypatch.setattr(module,'semantic_key',lambda engine:str(engine.k))
    monkeypatch.setattr(module,'periodic_gate',lambda result,period,k:dict(pass_gate=True,L_mean_s=result['requests'][0]['done_s'],S_mean_s=period))
    status=module.run_shard(('LPDDR5_c8',4))
    assert status['unique_runs']==3
    result=read_csv(tmp_path/'band/control_repair/shards/LPDDR5_c8_c4/runs.csv')
    assert all(float(r['L_s'])==int(r['dit_stages']) for r in result)
    with np.load(tmp_path/'band/control_repair/shards/LPDDR5_c8_c4/requests.npz') as data:
        assert set(data['requests'][:,0,3])=={1.,2.,3.}
