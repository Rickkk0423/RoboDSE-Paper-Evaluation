import pytest

from v6_task import METADATA,summarize


def test_task_protocols_count_invalid_separately():
    row=dict(point_id='example_only',speed_band='fixture',trials=10,successes=6,invalid_trials=2,
        **{k:'test_fixture_not_measurement' for k in METADATA})
    result=summarize([row])[0]
    assert result['success_rate_invalid_as_failure']==.6
    assert result['success_rate_invalid_excluded']==.75


def test_all_invalid_has_no_excluded_success_rate():
    row=dict(point_id='fixture',speed_band='fixture',trials=2,successes=0,invalid_trials=2,
        **{k:'fixture' for k in METADATA})
    assert summarize([row])[0]['success_rate_invalid_excluded'] is None
    with pytest.raises(ValueError):summarize([dict(row,successes=1)])


def test_missing_external_inputs_rejected():
    with pytest.raises(ValueError):summarize([dict(point_id='fixture')])
