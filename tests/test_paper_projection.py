"""Guard paper examples against peak-value substitution and extrapolation."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vlasim'))
from analysis.task_report import TaskGrid


def test_projection_does_not_substitute_peak():
    grid = TaskGrid(ROOT / 'vlasim/data/libero_dynamic_L_S.csv')
    k1 = grid.lookup(120.55426696313934, 120.5380793017601)
    k2 = grid.lookup(178.1640358152364, 89.07341015624652)
    assert k2['valid_only'] * 100 == pytest.approx(47.276804111188355)
    assert (k2['valid_only'] - k1['valid_only']) * 100 == pytest.approx(0.51966280339156)
    assert k2['valid_only'] < grid.lookup(200, 100)['valid_only']


@pytest.mark.parametrize('point', [(99, 50), (150, 49), (100, 150)])
def test_rectangular_bounds_are_not_hull_coverage(point):
    result = TaskGrid(ROOT / 'vlasim/data/libero_dynamic_L_S.csv').lookup(*point)
    assert result['status'] == 'outside_measured_hull'
    assert result['valid_only'] is None
