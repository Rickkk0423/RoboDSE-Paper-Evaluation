import numpy as np
import pytest

from v4_scheduler import (batch_means, observed_nonmonotonic, periodic_gate,
                          search_period, series_analysis, strict_groups)


def test_every_adjacent_group_checked():
    assert strict_groups([1, 2]*50, 2)['pass_gate']
    a = [1, 2]*50
    a[70] += 1e-5
    assert not strict_groups(a, 2)['pass_gate']
    assert not strict_groups([1, 2], 2)['pass_gate']


def test_fft_does_not_establish_periodicity():
    periodic = series_analysis([1., 2.]*100)
    assert periodic['classification'] == 'strict_periodic'
    assert periodic['strict_period_requests'] == 2
    drifting = series_analysis(np.arange(400)*.001+1)
    assert drifting['classification'] == 'drifting'
    quasi = series_analysis(1+.01*np.sin(np.arange(800)*np.sqrt(2)))
    assert quasi['strict_period_requests'] is None


def test_batch_means_label_and_interval():
    result = batch_means(np.arange(400))
    assert result['batches'] == 20
    assert result['ci95_s'][0] < result['mean_s'] < result['ci95_s'][1]
    assert 'not_independent' in result['interpretation']


def fixture_result():
    return dict(requests=[dict(steady_state=True, L_s=.5, S_s=.1) for _ in range(30)],
                vlm_queue=dict(steady_max_length=1))


def test_periodic_gate_all_conditions():
    result = fixture_result()
    assert periodic_gate(result, .1, 3)['pass_gate']
    result['requests'][15]['S_s'] += 1e-7
    assert not periodic_gate(result, .1, 3)['pass_gate']
    result = fixture_result()
    result['vlm_queue']['steady_max_length'] = 2
    assert not periodic_gate(result, .1, 3)['pass_gate']
    result = fixture_result()
    result['requests'][-1]['L_s'] += 1e-6
    assert not periodic_gate(result, .1, 3)['pass_gate']


def test_search_bracket_precision_and_upper_limit():
    result = search_period(lambda t: dict(pass_gate=t >= .12345), .01)
    assert .12345 <= result['Tmin_s'] < .12355
    assert result['bracket_width_s'] <= .0001
    exhausted = search_period(lambda t: dict(pass_gate=False), .01, cap=.02)
    assert exhausted['status'] == 'upper_bound_exhausted'
    assert exhausted['Tmin_s'] is None


def test_observed_nonmonotonicity_reported():
    assert observed_nonmonotonic({.1: dict(pass_gate=True), .2: dict(pass_gate=False)})
    assert not observed_nonmonotonic({.1: dict(pass_gate=False), .2: dict(pass_gate=True)})
