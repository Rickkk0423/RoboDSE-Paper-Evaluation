"""Summarize executed evidence without promoting missing science gates to passes."""
import argparse
import hashlib
import json
from pathlib import Path


def gates(state, compute, convergence, task):
    return [
        dict(name="native_execution", status="passed" if state["native_metadata"]["backend_executed"] else "failed",
             evidence="Pinned native Ramulator executed; simulator, not silicon."),
        dict(name="state_model_holdouts", status="passed" if all(g["gate"] == "pass" for k, g in state["groups"].items() if k != "unsupported_layout") else "blocked",
             evidence="All supported groups must pass, not only average error or selected subgroups."),
        dict(name="full_compute", status="blocked" if compute["strict_gate"] != "pass" else "passed",
             evidence=compute["strict_gate"] + "; hybrid results are not full-compute validation."),
        dict(name="sampled_interval_convergence", status="passed" if max(convergence["max_abs_L_delta_pct"], convergence["max_abs_S_delta_pct"]) <= 1 else "failed",
             evidence="30 vs 120 requests, all shortlisted candidates and sampled DRAM points."),
        dict(name="task_transfer", status="blocked", evidence=task["ranking_gate"]),
        dict(name="checkpoint_shapes", status="blocked", evidence="No deployed-checkpoint shape manifest and verification output supplied."),
        dict(name="area_energy", status="blocked", evidence="Only placeholder constants, no technology-specific measurements or source reports supplied."),
        dict(name="independent_vla_replay", status="blocked", evidence="No independent timestamped kernel/memory/RW capture or validated execution schedule supplied."),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "compute", "convergence", "task"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    paths = {n: getattr(args, n) for n in ("state", "compute", "convergence", "task")}
    reports = {n: json.loads(p.read_text()) for n, p in paths.items()}
    checks = gates(**reports)
    output = dict(status="blocked_for_final_architecture_claim" if any(g["status"] != "passed" for g in checks) else "ready",
                  gates=checks, evidence={n: dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n, p in paths.items()},
                  interpretation="Engineering artifacts and experiments can be complete while validation/measurement gates remain blocked. Do not report all science gates as complete.")
    (args.out / "completion_report.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"status": output["status"], "gates": checks}, indent=2))


if __name__ == "__main__":
    main()
