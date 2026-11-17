import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("state_model", Path(__file__).resolve().parents[1] / "vlasim/ramulator_bridge/state_model.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def test_state_features_are_directional_and_normalized():
    a = model.features_from_order([0, 0, 1, 0, 1, 1])
    b = model.features_from_order([1, 1, 0, 1, 0, 0])
    assert len(a) == len(model.FEATURES)
    assert sum(a[:10]) == pytest.approx(1)
    assert a != b


def test_fit_excludes_holdouts_and_unknown_layout_abstains():
    rows = [dict(split="train", shift_bytes=0, GBps=100 + i,
                 features=model.features_from_order([0, 1] * (10 + i))) for i in range(3)]
    fit = model.fit_model(rows)
    assert fit == model.fit_model(rows + [dict(split="test", shift_bytes=0, GBps=1, features=[999] * len(model.FEATURES))])
    assert model.predict(fit, 512, rows[0]["features"]) == (None, "unsupported_layout")
    assert 1 <= model.predict(fit, 0, rows[0]["features"])[0] <= 256


def test_holdout_design_unique_and_predeclared():
    cases = model.heldout_cases()
    assert len(cases) == len({r["case"] for r in cases}) == 34
    assert sum(r["split"] == "unsupported_layout" for r in cases) == 4


def test_invalid_features_fail_instead_of_silent_prediction():
    with pytest.raises(ValueError):
        model.features_from_order([])
    with pytest.raises(ValueError):
        model.features_from_order([0, 2])
    with pytest.raises(ValueError):
        model.fit_model([dict(split="train", shift_bytes=0, GBps=100, features=[np.nan] * len(model.FEATURES))])
