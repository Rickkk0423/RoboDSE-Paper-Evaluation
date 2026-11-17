import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("audit_plan", Path(__file__).resolve().parents[1] / "vlasim/audit_plan.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_selected_passes_cannot_mask_failed_or_missing_gates():
    checks = audit.gates(
        dict(native_metadata=dict(backend_executed=True), groups={"ratio": dict(gate="pass"), "burst": dict(gate="failed"), "unsupported_layout": dict(gate="abstained")}),
        dict(strict_gate="blocked_unresolved_siglip"),
        dict(max_abs_L_delta_pct=1e-9, max_abs_S_delta_pct=1e-9),
        dict(ranking_gate="blocked_unverified_task_transfer_and_cost"))
    states = {c["name"]: c["status"] for c in checks}
    assert states["native_execution"] == states["sampled_interval_convergence"] == "passed"
    assert states["state_model_holdouts"] == states["full_compute"] == states["area_energy"] == "blocked"
