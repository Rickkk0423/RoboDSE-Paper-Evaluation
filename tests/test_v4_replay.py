import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'vlasim/ramulator_bridge'))
    return importlib.import_module('v4_replay_native')


class Memory:
    tx_bytes, capacity_bytes, tck_ns = 32, 2**32, 1.

    def __init__(self):
        self.cycle, self.pending, self.sent = 0, [], []

    def send(self, rid, write, address, core):
        self.sent.append((self.cycle, write, address, core))
        self.pending.append((rid, self.cycle + 3))
        return True

    def tick(self):
        self.cycle += 1

    def completions(self):
        done = [x for x in self.pending if x[1] <= self.cycle]
        self.pending = [x for x in self.pending if x[1] > self.cycle]
        return done


def test_array_replay_stream_timestamps_writes_and_completion(replay, tmp_path):
    path = tmp_path / 'trace.npz'
    np.savez(path, issue_ns=np.arange(20) * 5., core=np.arange(20) % 2,
             address=np.arange(20, dtype=np.uint64) * 64, write=np.arange(20) % 3 == 0)
    memory = Memory()
    result = replay.execute_arrays(memory, path, channels=8, issue_width=2, outstanding=2)
    assert result['accepted'] == result['completed'] == 40
    assert result['stream_transactions'] == [20, 20]
    for cycle, write, address, core in memory.sent:
        assert cycle >= address // 64 * 5
        assert core == address // 64 % 2
        assert write == (address // 64 % 3 == 0)


def test_bg_shared_kv_uses_same_address_for_writer_and_reader(replay, tmp_path):
    path = tmp_path / 'trace.npz'
    np.savez(path, issue_ns=np.zeros(10), core=np.arange(10) % 2,
             address=np.zeros(10, dtype=np.uint64), write=np.arange(10) % 2 == 0,
             owner=np.ones(10, dtype=np.uint8))
    memory = Memory()
    replay.execute_arrays(memory, path, channels=8, issue_width=8,
                          bg_geometry=([1, 0, 2, 2, 14, 5], 2))
    writes = {a for _, w, a, _ in memory.sent if w}
    reads = {a for _, w, a, _ in memory.sent if not w}
    assert writes == reads


def test_array_replay_cycle_budget_is_not_a_pass(replay, tmp_path):
    path = tmp_path / 'trace.npz'
    np.savez(path, issue_ns=np.ones(10) * 100., core=np.zeros(10),
             address=np.arange(10, dtype=np.uint64) * 64, write=np.zeros(10))
    with pytest.raises(RuntimeError, match='cycle budget'):
        replay.execute_arrays(Memory(), path, channels=8, issue_width=8, max_cycles=5)
