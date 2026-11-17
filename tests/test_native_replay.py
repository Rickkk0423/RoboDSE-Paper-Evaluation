import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_native", ROOT / "vlasim/ramulator_bridge/run_native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class FakeMemory:
    tx_bytes = 32
    capacity_bytes = 2**32
    tck_ns = 1.0

    def __init__(self, reject_once=False):
        self.cycle = 0
        self.queue = []
        self.accepted = []
        self.reject_once = reject_once

    def send(self, rid, write, address, core):
        if self.reject_once:
            self.reject_once = False
            return False
        self.accepted.append((rid, self.cycle, write, address, core))
        self.queue.append((rid, self.cycle + 2))
        return True

    def tick(self):
        self.cycle += 1

    def completions(self):
        done = [r for r in self.queue if r[1] <= self.cycle]
        self.queue = [r for r in self.queue if r[1] > self.cycle]
        return done


def make_trace(tmp_path, text):
    path = tmp_path / "trace.csv"
    path.write_text(text)
    return path


def test_split_and_stream_write_semantics(tmp_path):
    trace = make_trace(tmp_path, "0,vlm,R,0x0\n5,kv,W,0x80000000\n")
    assert list(native.requests(trace, 32, 2**32)) == [
        (0, 0, False, 0), (0, 0, False, 32),
        (5, 1, True, 0x80000000), (5, 1, True, 0x80000020)]


@pytest.mark.parametrize("text", ["0,hi_dit,R,0x0\n", "0,vlm,X,0x0\n",
                                 "0,vlm,R,0x1\n", "nan,vlm,R,0x0\n",
                                 "2,vlm,R,0x0\n1,vlm,R,0x40\n",
                                 "0,vlm,R,0x100000000\n"])
def test_bad_trace_rejected(tmp_path, text):
    with pytest.raises(ValueError):
        list(native.requests(make_trace(tmp_path, text), 32, 2**32))


def test_timed_backpressure_and_completion_accounting(tmp_path):
    trace = make_trace(tmp_path, "0,vlm,R,0x0\n5,dit,R,0x40\n9,vlm,R,0x80\n")
    memory = FakeMemory(reject_once=True)
    report = native.execute(memory, trace, issue_width=1, outstanding=1, max_cycles=100)
    assert report["accepted"] == report["completed"] == 6
    assert report["rejected_attempts"] == 1
    assert report["logical_bytes"] == 192
    assert memory.accepted[0][1] == 1
    assert memory.accepted[2][1] >= 5
    assert memory.accepted[4][1] >= 9
    assert [r[3] for r in memory.accepted] == [0, 32, 64, 96, 128, 160]


def test_cycle_limit_does_not_report_success(tmp_path):
    with pytest.raises(RuntimeError, match="cycle budget"):
        native.execute(FakeMemory(), make_trace(tmp_path, "1000,vlm,R,0x0\n"),
                       issue_width=1, outstanding=1, max_cycles=3)


def test_no_transactions_dropped_at_issue_width(tmp_path):
    trace = make_trace(tmp_path, "".join(f"0,vlm,R,{i*64:#x}\n" for i in range(20)))
    report = native.execute(FakeMemory(), trace, issue_width=3, outstanding=7, max_cycles=100)
    assert report["completed"] == 40


def test_configured_space_excludes_unsupported_priority():
    from vlasim.dse import configured_space, mapping_space
    from vlasim import HWConfig
    space = configured_space(ROOT / "configs/dse_hbm2_8ch.json")
    assert len(space) == 60
    assert all(m.bw_policy == "fair" for h, m in space)
    assert all(not h.dram_priority and h.dram_bw == 256e9 for h, m in space)
    unsupported = mapping_space([HWConfig(n_cores=2, dram_priority=False)])
    assert not any(m.bw_policy == "vlm_priority" for h, m in unsupported)


def test_calibration_cannot_silently_transfer_to_other_hardware():
    from vlasim.dse import validate_calibration_space
    from vlasim import HWConfig, MapConfig
    cal = {"backend_metadata": {"backend_executed": True, "peak_GBps": 256,
                                "priority_supported": False}}
    validate_calibration_space(cal, [(HWConfig(dram_bw=256e9), MapConfig())])
    with pytest.raises(ValueError, match="bandwidth"):
        validate_calibration_space(cal, [(HWConfig(dram_bw=100e9), MapConfig())])
    with pytest.raises(ValueError, match="priority"):
        validate_calibration_space(cal, [(HWConfig(dram_bw=256e9), MapConfig(bw_policy="vlm_priority"))])


def test_coverage_window_requires_real_full_batch_overlap(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "vlasim/ramulator_bridge"))
    coverage_spec = importlib.util.spec_from_file_location("coverage_validation", ROOT / "vlasim/ramulator_bridge/validate_coverage.py")
    coverage = importlib.util.module_from_spec(coverage_spec)
    coverage_spec.loader.exec_module(coverage)
    timeline = [(0, 10, "vlm", "vlm", 100, (0,)),
                (1, 3, "dit", "dit", 100, (1,)),
                (4, 8, "dit", "dit", 100, (1, 2, 3))]
    start = coverage.select_window(timeline, ("vlm", "dit"), 1, 0, 10, min_batch=3)
    assert 4 <= start <= 7
    with pytest.raises(ValueError, match="no steady window"):
        coverage.select_window(timeline[:2], ("vlm", "dit"), 1, 0, 10, min_batch=3)
