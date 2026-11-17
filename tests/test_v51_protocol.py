import importlib
from pathlib import Path

import pytest


@pytest.fixture
def native_catalog(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'vlasim/ramulator_bridge'))
    return importlib.import_module('v51_catalog')


def test_memory_catalog_nominal_bus_widths_and_distinct_identities(native_catalog):
    rows = native_catalog.catalog()
    assert len(rows) == len({r['id'] for r in rows}) == 10
    assert [r['channels']*16 for r in rows if r['standard']=='GDDR6'] == [256,384,576]
    assert all(r['standard'] != 'GDDR6X' for r in rows)


def test_lpddr_spans_include_all_bank_domains_not_just_row_capacity(native_catalog):
    spans = native_catalog.row_spans([16,1,4,4,32768,1024],
                     ['Channel','Rank','BankGroup','Bank','Row','Column'],16,32,16)
    assert spans['physical_row_bytes']==2048
    assert spans['level1_bytes']==32768
    assert spans['level2_bytes']==524288
    assert spans['row_domains_per_channel']==16


def test_non_power_of_two_channels_preserve_span_arithmetic(native_catalog):
    spans = native_catalog.row_spans([24,4,4,16384,1024],
                     ['Channel','BankGroup','Bank','Row','Column'],16,32,24)
    assert spans['level1_bytes']==49152
    assert spans['level2_bytes']==786432


@pytest.mark.parametrize('singleton', [True,False])
def test_accounting_accepts_native_singleton_or_controller_list(native_catalog,tmp_path,singleton):
    import yaml
    controller = dict(num_read_reqs_served=9,num_read_reqs_forwarded=1)
    path = tmp_path/'stats.yaml'
    path.write_text(yaml.safe_dump(dict(memory_system=dict(total_num_read_requests=10,
        total_num_write_requests=0,controller=controller if singleton else [controller]))))
    native = dict(accepted=10,completed=10,stream_transactions=[4,6],logical_bytes=320)
    assert native_catalog.check_accounting(native,[path],[128,192])['passed']


@pytest.mark.parametrize('channels',[4,8,16,24,36])
def test_bounded_logical64_bg_is_exactly_native32_transform(native_catalog,channels):
    import numpy as np
    from v51_bg import map_addresses
    from channel_frontend import partition_address
    address=np.arange(10003,dtype=np.uint64)*64
    owners=(np.arange(len(address))%2).astype(np.uint8)
    geometry=([0,2,2,15,6],1)
    logical=map_addresses(address,owners,channels,geometry,chunk=713)
    native=np.repeat(address,2)+np.tile(np.array([0,32],dtype=np.uint64),len(address))
    expected=partition_address(native//32,np.repeat(owners,2).astype(np.uint64),channels,32,
                               mop_geometry=geometry)
    actual=np.repeat(logical,2)+np.tile(np.array([0,32],dtype=np.uint64),len(address))
    assert np.array_equal(actual,expected)
