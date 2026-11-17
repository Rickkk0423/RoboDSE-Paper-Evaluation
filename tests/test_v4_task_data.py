"""Synthetic fixtures only; none of these episodes is measured evidence."""
import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("v4_task_data", Path(__file__).resolve().parents[1] / "vlasim/v4_task_data.py")
task = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task)


def synthetic(index=0, valid=True, success=True, run="synthetic-test"):
    return dict(schema_version="v4-task-trial-v1", source_type="measured_closed_loop",
                benchmark="LIBERO-Dynamic", benchmark_version="synthetic-v1",
                run_id=run, trial_id=str(index), episode_id=str(index), task_id="synthetic-task", seed=index,
                L_ms=50, S_ms=25, speed=dict(value=.03, unit="m/s"),
                checkpoint=dict(id="synthetic", version="test-only", sha256="a" * 64),
                environment=dict(name="synthetic", version="test-only", simulator_version="test-only",
                                 dependency_lock_sha256="b" * 64),
                latency_injection=dict(method="synthetic", version="test-only", L_definition="test-L",
                                       S_definition="test-S", clock="test-clock", config={}),
                adoption=dict(strategy="synthetic", version="test-only", config={}),
                validity_protocol=dict(id="synthetic", version="test-only", definition="test-definition"),
                valid=valid, validity_reason="test-valid" if valid else "test-invalid",
                success=success, evidence_ref="synthetic-fixture-only")


def test_plan_exact_cartesian_coverage_and_no_assumed_speeds():
    rows = task.sampling_plan()
    assert len(rows) == 56
    assert len({(r["benchmark"], r["L_ms"], r["S_ms"]) for r in rows}) == 56
    for b in task.BENCHMARKS:
        subset = [r for r in rows if r["benchmark"] == b]
        assert sum(r["region"] == "low_latency" for r in subset) == 6
        assert sum(r["region"] == "plateau" for r in subset) == 22
    assert all(r["S_ms"] <= r["L_ms"] and r["speed_levels"] is None
               and r["episodes_per_speed"] is None for r in rows)


@pytest.mark.parametrize("field", list(task.trial_schema()["required"]))
def test_all_required_fields(field):
    row = synthetic()
    del row[field]
    with pytest.raises(ValueError):
        task.validate_trial(row)


@pytest.mark.parametrize("path,value", [
    (("L_ms",), float("nan")), (("S_ms",), 100), (("valid",), 1),
    (("success",), "true"), (("seed",), True), (("speed", "value"), 0),
    (("checkpoint", "sha256"), "not-a-hash"), (("environment", "version"), "unknown"),
    (("latency_injection", "version"), None), (("adoption", "strategy"), ""),
    (("validity_reason",), "  "), (("source_type",), "synthetic"),
    (("latency_injection", "config"), {"x": float("inf")}),
])
def test_bad_trials(path, value):
    row = synthetic()
    target = row
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        task.validate_trial(row)


def test_pool_counts_not_mean_of_rates_and_two_invalid_conventions():
    rows = [synthetic(0, run="first")]
    rows += [synthetic(i, success=False, run="second") for i in range(3)]
    rows += [synthetic(4, valid=False, success=False)]
    result = {r["invalid_policy"]: r for r in task.aggregate(rows)}
    failure, exclude = result["invalid_as_failure"], result["exclude_invalid"]
    assert failure["n_trials"] == 5 and failure["n_invalid"] == 1
    assert failure["success_rate"] == .2
    assert exclude["success_rate"] == .25  # Not (.0 + 1.0) / 2.
    assert exclude["binomial_standard_error"] == pytest.approx(math.sqrt(.25 * .75 / 4))
    assert failure["binomial_standard_error"] == pytest.approx(math.sqrt(.2 * .8 / 5))


@pytest.mark.parametrize("field,value", [
    ("benchmark", "LIBERO-Long"), ("benchmark_version", "other"), ("L_ms", 75), ("S_ms", 50),
    ("speed", dict(value=.06, unit="m/s")),
    ("checkpoint", dict(id="synthetic", version="different", sha256="c" * 64)),
    ("environment", dict(name="synthetic", version="other", simulator_version="other", dependency_lock_sha256="d" * 64)),
    ("adoption", dict(strategy="other", version="test-only", config={})),
    ("latency_injection", dict(method="other", version="v2", L_definition="L", S_definition="S", clock="c", config={})),
    ("validity_protocol", dict(id="other", version="v2", definition="different")),
])
def test_protocol_groups_never_mixed(field, value):
    rows = [synthetic(0), synthetic(1)]
    rows[1][field] = value
    assert len(task.aggregate(rows)) == 4


def test_all_invalid_and_empty():
    rows = task.aggregate([synthetic(valid=False, success=False)])
    assert rows[0]["success_rate"] == 0
    assert rows[1]["success_rate"] is None
    assert rows[1]["binomial_standard_error"] is None
    assert rows[1]["status"] == "no_valid_trials"
    assert task.aggregate([]) == []
    with pytest.raises(ValueError):
        task.validate_trial(synthetic(valid=False, success=True))


def test_equivalent_numeric_fields_pool_together():
    rows = [synthetic(0), synthetic(1)]
    rows[1].update(L_ms=50.0, S_ms=25.0)
    assert len(task.aggregate(rows)) == 2


def test_jsonl_errors_and_duplicate_episodes(tmp_path):
    path = tmp_path / "synthetic.jsonl"
    row = synthetic()
    path.write_text(json.dumps(row) + "\n")
    assert task.load_trials(path) == [row]
    other = copy.deepcopy(row)
    other["trial_id"] = "different-but-same-episode"
    for bad in (json.dumps(row), json.dumps(other), "", '{"valid":true,"valid":false}', "broken"):
        path.write_text(json.dumps(row) + "\n" + bad + "\n")
        with pytest.raises(ValueError, match=":2:"):
            task.load_trials(path)
    with pytest.raises(ValueError, match="duplicate"):
        task.aggregate([row, other])


def test_template_cannot_be_ingested_and_schema_complete():
    template = task.example_template()
    assert template["artifact_type"] == "non_measured_template_not_ingestible"
    with pytest.raises(ValueError):
        task.validate_trial(template)
    with pytest.raises(ValueError):
        task.validate_trial(template["trial_template"])
    assert task.trial_schema()["additionalProperties"] is False


def test_prepare_only_writes_nonmeasured_artifacts(tmp_path):
    csv = tmp_path / "legacy.csv"
    csv.write_text("L,S,valid,a,b,c,mean\n100,50,10,0,0,0,0\n")
    spec = tmp_path / "spec.md"
    spec.write_text("test spec")
    out = tmp_path / "out"
    result = task.prepare(out, csv, spec)
    assert result["status"] == "blocked_missing_closed_loop_environment"
    assert result["measured_trials"] == 0
    assert len(list(out.iterdir())) == 3
    assert result["legacy_csv"]["per_speed_denominators"] is None
    assert result["legacy_csv"]["speed_header_values_m_s"] == []
    with pytest.raises(FileExistsError):
        task.prepare(out, csv, spec)
