import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vlasim'))
from v7_common import dominates, feasible, pareto, resource
from v7_cost import area_feature
from v7_pareto import classify
from v7_validate import accounting, engine_identity, scenarios


def row(cores=4, bw=100, sram=8, private=512, mode='serial', L=.08, S=.09, **extra):
    return dict(n_cores=cores, actual_peak_GBps=bw, sram_mb=sram, local_kb=private,
                mode=mode, L_s=L, S_s=S, memory='LPDDR5_c8', **extra)


def test_strict_dominance_not_equality():
    assert not dominates((4, 100), (4, 100))
    assert dominates((3, 100), (4, 100))
    assert not dominates((3, 200), (4, 100))


def test_pareto_preserves_all_resource_tied_designs():
    a, b, c = row(), row(sram=64), row(cores=8)
    assert pareto([a, b, c]) == [a, b]


def test_sram_third_dimension_changes_frontier():
    a, b = row(cores=3, sram=64), row(cores=4, sram=8)
    assert pareto([a, b]) == [a]
    assert pareto([a, b], True) == [a, b]


def test_private_sram_decimal_units():
    assert resource(row(), True)[2] == pytest.approx(8 + 4 * 512 * 1024 / 1e6)


def test_latency_only_uses_Smax_as_latency_bound():
    assert feasible(row(L=.09, S=.2), 200, 100, 'latency_only')
    assert not feasible(row(L=.11), 200, 100, 'latency_only')
    assert not feasible(row(mode='pipelined'), 200, 100, 'latency_only')


def test_task_requires_both_L_and_S():
    assert feasible(row(L=.18, S=.09), 200, 100, 'task_aware')
    assert not feasible(row(L=.21, S=.09), 200, 100, 'task_aware')
    assert not feasible(row(L=.18, S=.11), 200, 100, 'task_aware')


@pytest.mark.parametrize('lat,task,expected', [
    ([row()], [row(sram=64)], 'identical'),
    ([row(cores=8)], [row(cores=4)], 'task_strictly_better'),
    ([row()], [row(), row(cores=3, bw=200)], 'task_extends'),
    ([], [row()], 'lat_infeasible_task_feasible'),
])
def test_relationships(lat, task, expected):
    assert classify(lat, task) == expected


def test_phy_area_feature_counts_channels_not_GBps():
    assert np.array_equal(area_feature(row()), [4, 10.097152, 1, 8, 0, 0])


def test_gddr_phy_correlation_formula():
    hbm = np.array([.23, .27, .93])
    ratio = np.array([1.5, 1.625, 1.75])
    gddr = hbm / 32 * 28 * ratio
    np.testing.assert_allclose(gddr / hbm, ratio * 28 / 32)


def test_engine_cache_does_not_alias_blank_config_ids():
    a = dict(config_id='', hardware_id='same', dit_stages='1', dit_batching='True')
    b = dict(a, dit_stages='2')
    assert engine_identity(a) != engine_identity(b)


def test_round_time_failure_hard_stops():
    result = dict(dit_rounds=[dict(duration_s=1., compute_s=.4, exposed_memory_s=.1,
                                  linear_s=.5, attention_s=.5)])
    with pytest.raises(RuntimeError, match='HARD_STOP_round_time_conservation'):
        accounting(result, None)


def test_same_type_energy_factor_cancels_across_interval():
    baseline, task = 11.331160064, 8.2
    ratios = [(task * 8 * e) / (baseline * 8 * e) for e in (2., 4., 6.)]
    np.testing.assert_allclose(ratios, task / baseline, rtol=1e-15)


def test_all_patch_coefficients_preserve_other_v6_values():
    import json
    base = Path('results/v7/inputs/cost/coefficients.json')
    patch = Path('results/v7/cost/coefficients.json')
    if not base.exists() or not patch.exists():
        pytest.skip('Optional generated V7 evidence not available')
    old = json.loads(base.read_text())['coefficients']
    new = json.loads(patch.read_text())
    changed = {'A_phy_LPDDR5', 'A_phy_GDDR6', 'e_dram_LPDDR5', 'e_dram_GDDR6'}
    assert all(v == new['coefficients'][k] for k, v in old.items() if k not in changed)
    assert new['cross_type_energy_comparable'] is False
    assert all(new['coefficients'][k]['source_type'] in {'academic', 'vendor', 'derived_ratio'} for k in changed)


def test_recheck_plan_covers_f3_and_frontiers():
    from v7_common import read_csv
    base = Path('results/v7/paper/pre_recheck')
    plan = Path('results/v7/validation/recheck_plan.csv')
    if not plan.exists():
        pytest.skip('Optional executed V7 recheck evidence not available')
    planned = {r['point_id'] for r in read_csv(plan)}
    for name in ('F3_all_feasible_points.csv', 'pareto_frontier_points.csv'):
        assert {r['point_id'] for r in read_csv(base/name)} <= planned


def test_task_request_has_required_low_and_outside_controls():
    from v7_common import read_csv
    path = Path('results/v7/task/selected_points.csv')
    if not path.exists():
        pytest.skip('Optional V7 task proposal not generated')
    rows = read_csv(path)
    assert len(rows) <= 16
    assert len({r['point_id'] for r in rows}) == len(rows)
    low = [r for r in rows if r['priority'] == '3']
    outside = [r for r in rows if r['priority'] == '4']
    assert len(low) == 4 and all(float(r['L_960_ms']) < 100 for r in low)
    assert len(outside) >= 2
    assert all(float(r['L_960_ms']) > 300 or float(r['S_960_ms']) > 150 for r in outside)


def test_empirical_scenarios_keep_unmeasured_W1_dit_unchanged():
    if not Path('results/v7/inputs/band/quantiles.json').exists():
        pytest.skip('Optional empirical scenario inputs absent')
    rows = list(scenarios('LPDDR5'))
    assert len(rows) == 30
    w1 = [r for r in rows if r[0] == 'W1']
    assert len(w1) == 3
    assert all(r[2] == 'unmeasured_unchanged' and r[3][1] == 1 for r in w1)
