import numpy as np
import pytest

from v6_cost import coefficient,estimate,feature
from v6_paper import BOXES,best,primary,latency_candidate


def test_box_grid_is_exact():
    assert len(BOXES)==22
    assert all(s<=l for l,s in BOXES)
    assert (100,150) not in BOXES and (300,200) in BOXES


def test_cost_feature_converts_private_kib_to_decimal_mb():
    assert feature(dict(n_cores=4,sram_mb=64,local_kb=512))==pytest.approx([4,66.097152,1])


def test_unknown_cost_is_not_silently_zero():
    c={k:coefficient(1.,.5,2.,'u',{},'test') for k in ('A_core','a_sram','A_misc','e_mac','leakage_density')}
    c['A_phy_LPDDR5']=coefficient(None,None,None,'u',{},'missing')
    c['e_dram_LPDDR5']=coefficient(None,None,None,'u',{},'missing')
    result=estimate(dict(memory='LPDDR5_c8',n_cores=4,sram_mb=64,local_kb=512,T_s=.1),c)
    assert result['area_value_mm2'] is None and result['energy_value_mJ'] is None
    assert result['DRAM_bytes_per_req'] is None
    assert result['static_energy_value_mJ'] is None
    assert result['known_components_area_value_mm2']>0


def test_known_energy_is_MAC_plus_DRAM_with_separate_static():
    c={k:coefficient(1.,.5,2.,'u',{},'test') for k in ('A_core','a_sram','A_misc','e_mac','leakage_density','A_phy_HBM2','e_dram_HBM2')}
    result=estimate(dict(memory='HBM2_c8',n_cores=4,sram_mb=64,local_kb=512,T_s=.1,
        steady_dram_GB_per_req=2.),c)
    expected=(result['MACs_per_req']+2e9*8)*1e-9
    assert result['energy_value_mJ']==pytest.approx(expected)
    assert result['static_energy_value_mJ']==pytest.approx(result['area_value_mm2']*.1*1000)
    assert result['energy_lower_mJ']<=result['energy_value_mJ']<=result['energy_upper_mJ']


def test_common_phy_cancels_only_in_within_tier_pair():
    a=dict(point_id='a',n_cores=8,sram_mb=64,local_kb=512,L_s=.1,S_s=.1)
    b=dict(point_id='b',n_cores=4,sram_mb=64,local_kb=512,L_s=.2,S_s=.1)
    c=np.array([5.,.2,1.])
    assert best([a,b],c) is b
    assert (feature(b)-feature(a))@c<0


def test_primary_excludes_sliced_background_and_baseline():
    r=dict(model='v51',track='neusim_unsliced',bw_policy='fair',bg='False')
    assert primary(r)
    assert not primary(dict(r,bg='True'))
    assert not primary(dict(r,model='v3_form'))


def test_serial_latency_baseline_uses_fastest_stable_period():
    row=dict(mode='serial',L_s=.09,Tmin_s=.091,T_s=.091)
    assert latency_candidate(row,100)
    assert not latency_candidate(dict(row,T_s=.182),100)
