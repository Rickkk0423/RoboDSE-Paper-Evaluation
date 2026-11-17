import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("scipy")
spec = importlib.util.spec_from_file_location("task_report", Path(__file__).resolve().parents[1] / "vlasim/analysis/task_report.py")
task = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task)


def test_task_grid_abstains_and_preserves_denominator_conventions(tmp_path):
    path = tmp_path / "grid.csv"
    path.write_text("L,S,valid,a,b,c,mean\n100,50,180,50,50,50,50\n200,50,360,50,50,50,50\n100,100,360,50,50,50,50\n")
    grid = task.TaskGrid(path)
    assert grid.lookup(100, 50)["valid_only"] == .5
    assert grid.lookup(100, 50)["coverage_weighted_proxy"] == .25
    assert grid.lookup(0, 0)["status"] == "outside_measured_hull"
    assert grid.lookup(100, 50 - 1e-11)["boundary_adjusted"] is True
    assert grid.lookup(100, 50 - 1e-4)["status"] == "outside_measured_hull"


def test_invalid_grid_rejected(tmp_path):
    path = tmp_path / "grid.csv"
    path.write_text("L,S,valid,a,b,c,mean\n100,50,0,50,50,50,50\n")
    with pytest.raises(ValueError):
        task.TaskGrid(path)


def test_candidate_identity_normalizes_numeric_csv_representations():
    assert task.identity(dict(hw_n_cores="2", map_mode="serial", map_kv_on_chip="")) == task.identity(
        dict(hw_n_cores="2.0", map_mode="serial", map_kv_on_chip="None"))


def test_compatibility_surface_has_unknown_error_and_no_implicit_extrapolation(tmp_path, monkeypatch):
    import math
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "vlasim/analysis"))
    from surface import SuccessSurface
    path = tmp_path / "grid.csv"
    path.write_text("L,S,valid,a,b,c,mean\n100,50,180,50,50,50,50\n200,50,360,50,50,50,50\n100,100,360,50,50,50,50\n")
    surface = SuccessSurface(path)
    assert surface(100, 50) == (.5, None, False)
    assert math.isnan(surface(0, 0)[0])
    with pytest.raises(ValueError, match="denominators"):
        SuccessSurface(path, invalid_as_fail=True)
