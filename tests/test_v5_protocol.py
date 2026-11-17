import numpy as np
import pytest

from v5_protocol import block_indices, offered


def test_blocks_keep_locality_and_exact_tenth():
    indices = block_indices(0,3200,2048)
    assert len(indices)==320
    assert np.array_equal(indices[:32],np.arange(32))
    assert indices[32]==320
    assert np.array_equal(np.concatenate([block_indices(a,b,2048) for a,b in ((0,13),(13,600),(600,3200))]),indices)


def test_block_clipping_and_phase():
    assert np.array_equal(block_indices(3,70,2048),np.arange(3,32))
    assert np.array_equal(block_indices(0,640,2048,phase=1),np.r_[np.arange(32,64),np.arange(352,384)])
    with pytest.raises(ValueError):
        block_indices(0,100,65)


def test_saturation_preserves_stream_order_and_byte_counts():
    arrays=dict(core=np.array([0,1,0,0,1],dtype=np.uint8),address=np.arange(5),
                issue_ns=np.arange(5),write=np.zeros(5),owner=np.zeros(5))
    output=offered(arrays,'saturated')
    assert np.array_equal(output['issue_ns'],np.zeros(5))
    for c in (0,1):
        assert np.array_equal(output['address'][output['core']==c],arrays['address'][arrays['core']==c])


def test_serial_keeps_phase_order_and_drain_barriers():
    arrays=dict(core=np.array([0,0,1,1,0],dtype=np.uint8),address=np.arange(5),issue_ns=np.arange(5))
    result=offered(arrays,'saturated',serial=True)
    assert np.array_equal(result['address'],arrays['address'])
    assert np.array_equal(result['epoch'],[0,0,1,1,2])
    assert 'epoch' not in arrays
