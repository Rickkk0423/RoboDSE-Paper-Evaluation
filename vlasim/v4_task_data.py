"""P1-B collection plan and strict measured-trial ingestion (no task execution)."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re


BENCHMARKS = ("LIBERO-Dynamic", "LIBERO-Long")
GROUP_FIELDS = (
    "benchmark", "benchmark_version", "L_ms", "S_ms", "speed", "checkpoint",
    "environment", "latency_injection", "adoption", "validity_protocol",
)


def text():
    return {"type": "string", "minLength": 1}


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def trial_schema():
    """JSON Schema for one measured episode; examples are deliberately not trials."""
    positive = {"type": "number", "exclusiveMinimum": 0}
    schema = obj({
        "schema_version": {"const": "v4-task-trial-v1"},
        "source_type": {"const": "measured_closed_loop"},
        "benchmark": {"enum": list(BENCHMARKS)}, "benchmark_version": text(),
        "run_id": text(), "trial_id": text(), "episode_id": text(),
        "task_id": text(), "seed": {"type": "integer", "minimum": 0},
        "L_ms": positive, "S_ms": positive,
        "speed": obj({"value": positive, "unit": {"const": "m/s"}}),
        "checkpoint": obj({"id": text(), "version": text(),
                           "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}),
        "environment": obj({"name": text(), "version": text(),
                            "simulator_version": text(), "dependency_lock_sha256": {
                                "type": "string", "pattern": "^[0-9a-f]{64}$"}}),
        "latency_injection": obj({"method": text(), "version": text(),
                                  "L_definition": text(), "S_definition": text(),
                                  "clock": text(), "config": {"type": "object"}}),
        "adoption": obj({"strategy": text(), "version": text(),
                         "config": {"type": "object"}}),
        "validity_protocol": obj({"id": text(), "version": text(), "definition": text()}),
        "valid": {"type": "boolean"}, "validity_reason": text(),
        "success": {"type": "boolean"}, "evidence_ref": text(),
    })
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["allOf"] = [{"if": {"properties": {"valid": {"const": False}}},
                         "then": {"properties": {"success": {"const": False}}}}]
    schema["$comment"] = "Additional semantic constraint: S_ms <= L_ms. Unknown metadata is rejected."
    return schema


def _check(value, schema, path):
    kind = schema.get("type")
    matches = {
        "object": isinstance(value, dict), "string": isinstance(value, str),
        "number": type(value) in (int, float) and math.isfinite(value),
        "integer": type(value) is int, "boolean": type(value) is bool,
    }
    if kind and not matches[kind]:
        raise ValueError(f"{path}: expected {kind}")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ValueError(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if kind == "object":
        missing = set(schema.get("required", [])) - value.keys()
        extra = value.keys() - schema.get("properties", {}).keys()
        if missing or (schema.get("additionalProperties") is False and extra):
            raise ValueError(f"{path}: missing={sorted(missing)} unexpected={sorted(extra)}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                _check(value[key], sub, f"{path}.{key}")
    if kind == "string":
        if not value.strip() or value.strip().lower() in {"unknown", "null", "none", "tbd", "pending", "待提供"}:
            raise ValueError(f"{path}: missing provenance")
        if "pattern" in schema:
            if not re.fullmatch(schema["pattern"], value):
                raise ValueError(f"{path}: invalid SHA-256")
    if kind in ("number", "integer"):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path}: must be positive")


def validate_trial(trial):
    _check(trial, trial_schema(), "trial")
    # Opaque protocol configs must also be portable strict JSON, never NaN/Infinity.
    try:
        json.dumps(trial, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("trial: non-JSON protocol config") from exc
    if trial["S_ms"] > trial["L_ms"]:
        raise ValueError("trial: S_ms must not exceed L_ms")
    if not trial["valid"] and trial["success"]:
        raise ValueError("trial: invalid episode cannot claim success")
    return trial


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_trials(path):
    trials, seen = [], set()
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                if not line.strip():
                    raise ValueError("blank JSONL line")
                trial = validate_trial(json.loads(line, object_pairs_hook=_unique_object))
                identity = (trial["run_id"], trial["trial_id"])
                episode = (trial["run_id"], trial["benchmark"], trial["task_id"], trial["episode_id"])
                if ("trial", identity) in seen or ("episode", episode) in seen:
                    raise ValueError("duplicate trial or episode within run")
                seen.update({("trial", identity), ("episode", episode)})
                trials.append(trial)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return trials


def aggregate(trials):
    """Pool episode counts, never average per-run or per-task success rates."""
    groups = defaultdict(list)
    seen = set()
    for trial in trials:
        validate_trial(trial)
        identities = (("trial", trial["run_id"], trial["trial_id"]),
                      ("episode", trial["run_id"], trial["benchmark"], trial["task_id"], trial["episode_id"]))
        if any(i in seen for i in identities):
            raise ValueError("duplicate trial or episode within run")
        seen.update(identities)
        group = {field: trial[field] for field in GROUP_FIELDS}
        group.update(L_ms=float(trial["L_ms"]), S_ms=float(trial["S_ms"]),
                     speed=dict(value=float(trial["speed"]["value"]), unit=trial["speed"]["unit"]))
        key = json.dumps(group, sort_keys=True, allow_nan=False)
        groups[key].append(trial)
    rows = []
    for key, episodes in sorted(groups.items()):
        valid = sum(t["valid"] for t in episodes)
        successes = sum(t["success"] and t["valid"] for t in episodes)
        for policy, n in (("invalid_as_failure", len(episodes)), ("exclude_invalid", valid)):
            p = successes / n if n else None
            rows.append(dict(**json.loads(key), invalid_policy=policy,
                             n_trials=len(episodes), n_valid=valid, n_invalid=len(episodes) - valid,
                             n_success=successes, denominator=n, success_rate=p,
                             binomial_standard_error=math.sqrt(p * (1 - p) / n) if n else None,
                             status="estimated" if n else "no_valid_trials",
                             standard_error_scope="pooled_binomial_plugin_not_cluster_adjusted",
                             run_ids=sorted({t["run_id"] for t in episodes})))
    return rows


def sampling_plan():
    points = [("low_latency", l, s) for l in (25, 50, 75) for s in (25, 50, 75) if s <= l]
    points += [("plateau", l, s) for l in (100, 125, 150, 175, 200, 250)
               for s in (50, 75, 100, 150) if s <= l]
    return [dict(benchmark=b, region=region, L_ms=l, S_ms=s,
                 speed_levels=None, episodes_per_speed=None,
                 status="pending_protocol_and_closed_loop_environment")
            for b in BENCHMARKS for region, l, s in points]


def example_template():
    def blank(schema):
        if "const" in schema:
            return schema["const"]
        if schema.get("type") == "object":
            return {k: blank(v) for k, v in schema.get("properties", {}).items()}
        return None
    return dict(artifact_type="non_measured_template_not_ingestible",
                warning="Nulls require real collection metadata; this is not an episode or evidence.",
                trial_template=blank(trial_schema()))


def prepare(out, source_csv, spec):
    out.mkdir(parents=True, exist_ok=True)
    with source_csv.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    speed_headers = [float(match.group(1)) for field in (fields or [])
                     if (match := re.fullmatch(r"([0-9]+(?:\.[0-9]+)?) m/s \(%\)", field))]
    plan = dict(status="blocked_missing_closed_loop_environment", measured_trials=0,
                benchmarks=list(BENCHMARKS), points=sampling_plan(), point_count=56,
                speed_protocol_status="must_be_provided_for_each_benchmark",
                episode_budget_status="must_be_provided_per_point_per_speed",
                missing_inputs=["verified_pi0.5_checkpoint_and_sha256", "executable_closed_loop_environment",
                                "benchmark_environment_and_dependency_versions", "benchmark_speed_protocols",
                                "per_speed_episode_budgets", "latency_injection_and_adoption_protocols",
                                "invalid_episode_definition", "trial_level_episode_evidence"],
                legacy_csv=dict(path=str(source_csv), sha256=hashlib.sha256(source_csv.read_bytes()).hexdigest(),
                                rows=len(rows), fields=fields,
                                scope="aggregate_only_not_trial_evidence_not_ingested",
                                speed_header_values_m_s=speed_headers,
                                speed_values_apply_to_new_benchmarks=False,
                                per_speed_denominators=None, checkpoint=None, environment_version=None),
                spec_sha256=hashlib.sha256(spec.read_bytes()).hexdigest())
    for name, value in (("sampling_plan.json", plan), ("trial.schema.json", trial_schema()),
                        ("example.template.json", example_template())):
        path = out / name
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
        path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--out", type=Path, required=True)
    prep.add_argument("--source-csv", type=Path, required=True)
    prep.add_argument("--spec", type=Path, required=True)
    pool = sub.add_parser("aggregate")
    pool.add_argument("trials", type=Path)
    pool.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.out, args.source_csv, args.spec)
        print(json.dumps({k: result[k] for k in ("status", "point_count", "measured_trials")}))
    else:
        trials = load_trials(args.trials)
        result = dict(source_sha256=hashlib.sha256(args.trials.read_bytes()).hexdigest(),
                      measured_trials=len(trials), estimates=aggregate(trials),
                      status="aggregated" if trials else "no_trials")
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    main()
