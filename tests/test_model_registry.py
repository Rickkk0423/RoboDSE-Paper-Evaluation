import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vlasim'))
from vlasim.model_registry import load_workload
from vlasim.dynamicvla_workload import DynamicVLAWorkload
from vlasim.workload import Pi05Workload


def test_registry_preserves_pi05_default():
    assert isinstance(load_workload('pi05'), Pi05Workload)
    assert isinstance(load_workload('pi_0_5'), Pi05Workload)


def test_registry_loads_dynamicvla_profile():
    path = Path(__file__).resolve().parents[1] / 'publication/dynamicvla_pilot/profile.json'
    assert isinstance(load_workload('dynamicvla', profile=path), DynamicVLAWorkload)
    with pytest.raises(ValueError, match='requires'):
        load_workload('dynamicvla')
