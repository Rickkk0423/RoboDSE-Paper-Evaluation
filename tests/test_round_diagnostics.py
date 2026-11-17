import math

import pytest

from vlasim import HWConfig, MapConfig, Simulator


@pytest.mark.parametrize("mode,k", [("serial", 1), ("pipelined", 1), ("pipelined", 2)])
def test_round_diagnostics_preserve_results_and_reconcile_time_bytes(mode, k):
    hw = HWConfig(n_cores=4)
    mp = MapConfig(mode=mode, dit_stages=k)
    ordinary = Simulator(hw, mp).run(n_requests=20, warmup=4)
    result = Simulator(hw, mp).run(n_requests=20, warmup=4, diagnostics=True)
    for key in ordinary:
        assert result[key] == ordinary[key]
    rounds = result["dit_rounds"]
    for r in rounds:
        assert math.isclose(r["duration_s"], r["compute_s"] + r["exposed_memory_s"], abs_tol=1e-12)
        assert math.isclose(r["duration_s"], r["linear_s"] + r["attention_s"], abs_tol=1e-12)
        assert r["exposed_memory_s"] >= 0 and r["wait_before_s"] >= -1e-12
    assert math.isclose(sum(r["dram_bytes"] for r in rounds) / 20 / 1e9,
                        result["dit_GB_per_req"], abs_tol=1e-12)
    assert math.isclose(sum(r["duration_s"] for r in rounds) / result["makespan_s"],
                        result["dit_busy"], abs_tol=1e-12)
