import importlib
from pathlib import Path

import pytest


@pytest.fixture
def frontend(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "vlasim/ramulator_bridge"))
    return importlib.import_module("channel_frontend")


def test_partition_channel_sets_and_unique_addresses(frontend):
    for fraction in (.5, .625, .75):
        streams = [{frontend.partition_address(i, core, 8, 32, fraction) for i in range(4096)} for core in (0, 1)]
        assert len(streams[0]) == len(streams[1]) == 4096
        assert streams[0].isdisjoint(streams[1])
        channels = [{frontend.channel_for(a, 32, 8) for a in stream} for stream in streams]
        assert channels[0].isdisjoint(channels[1])
        assert len(channels[0]) == 8 * fraction


@pytest.mark.parametrize('bits,bg', [([0, 0, 2, 2, 14, 6], 2), ([0, 2, 2, 16, 6], 1),
                                  ([1, 0, 2, 2, 14, 5], 2), ([0, 2, 2, 15, 6], 1)])
def test_mop_inverse_and_partition(frontend, bits, bg):
    for intra in range(65536):
        assert frontend.mop_encode(frontend.mop_decode(intra, bits), bits) == intra
    streams = []
    for core in (0, 1):
        stream = {frontend.partition_address(i, core, 8, 32, mop_geometry=(bits, bg)) for i in range(32768)}
        assert len(stream) == 32768
        assert {frontend.mop_decode(a // 32 // 8, bits)[bg] for a in stream} == ({0, 1} if core == 0 else {2, 3})
        assert {frontend.channel_for(a, 32, 8) for a in stream} == set(range(8))
        streams.append(stream)
    assert streams[0].isdisjoint(streams[1])


def test_mop_hbm_known_source_vectors(frontend):
    bits = [1, 0, 2, 2, 14, 5]
    vectors = {0: [0, 0, 0, 0, 0, 0], 1: [1, 0, 0, 0, 0, 1],
               2: [0, 0, 1, 0, 0, 2], 4: [1, 0, 0, 0, 0, 0],
               128: [0, 0, 2, 0, 0, 4], 512: [0, 0, 0, 2, 0, 16],
               1024: [0, 0, 0, 0, 1, 0]}
    for address, fields in vectors.items():
        assert frontend.mop_decode(address, bits) == fields
        assert frontend.mop_encode(fields, bits) == address


@pytest.mark.parametrize("shift", [5, 6])
def test_bank_groups_disjoint_while_channels_shared(frontend, shift):
    streams = [[frontend.partition_address(i, core, 8, 32, bg_geometry=(shift, 2)) for i in range(8192)] for core in (0, 1)]
    bgs = [{((a // 32 // 8) >> shift) & 3 for a in stream} for stream in streams]
    assert bgs == [{0, 1}, {2, 3}]
    assert all({frontend.channel_for(a, 32, 8) for a in stream} == set(range(8)) for stream in streams)
    assert set(streams[0]).isdisjoint(streams[1])


def test_blocked_channel_does_not_block_other_channels(frontend, tmp_path):
    class Memory:
        tx_bytes, capacity_bytes, tck_ns = 32, 2**32, 1.0
        def __init__(self):
            self.cycle, self.pending, self.accepted = 0, [], []
        def send(self, rid, write, address, core):
            if address // 32 % 2 == 0 and self.cycle < 4:
                return False
            self.pending.append((rid, self.cycle + 2))
            self.accepted.append((self.cycle, address))
            return True
        def tick(self):
            self.cycle += 1
        def completions(self):
            done = [p for p in self.pending if p[1] <= self.cycle]
            self.pending = [p for p in self.pending if p[1] > self.cycle]
            return done
    trace = tmp_path / "trace.csv"
    trace.write_text("".join(f"0,vlm,R,{i * 64:#x}\n" for i in range(20)))
    memory = Memory()
    r = frontend.execute(memory, trace, channels=2, issue_width=2, outstanding=8, max_cycles=100)
    assert memory.accepted[0] == (0, 32)
    assert r["bypass_cycles"] > 0
    assert r["accepted"] == r["completed"] == 40


def test_nonblocking_preserves_timestamps_limits_and_per_channel_order(frontend, tmp_path):
    class Memory:
        tx_bytes, capacity_bytes, tck_ns = 32, 2**32, 1.0
        def __init__(self):
            self.cycle, self.pending, self.accepted, self.max_pending = 0, [], [], 0
        def send(self, rid, write, address, core):
            self.pending.append((rid, self.cycle + 3))
            self.accepted.append((self.cycle, address, core, write))
            self.max_pending = max(self.max_pending, len(self.pending))
            return True
        def tick(self):
            self.cycle += 1
        def completions(self):
            done = [p for p in self.pending if p[1] <= self.cycle]
            self.pending = [p for p in self.pending if p[1] > self.cycle]
            return done
    trace = tmp_path / "trace.csv"
    trace.write_text("0,vlm,R,0x0\n10,dit,W,0x40\n20,vlm,R,0x80\n30,dit,R,0xc0\n")
    memory = Memory()
    r = frontend.execute(memory, trace, channels=2, issue_width=1, outstanding=1, max_cycles=100)
    assert r["accepted"] == r["completed"] == 8
    assert memory.max_pending == 1
    for cycle, address, core, write in memory.accepted:
        assert cycle >= (address // 64) * 10
        assert core == (address // 64) % 2
        assert write == (address // 64 == 1)
    for channel in (0, 1):
        assert [a for _, a, _, _ in memory.accepted if a // 32 % 2 == channel] == list(range(channel * 32, 256, 64))
    with pytest.raises(RuntimeError, match="cycle budget"):
        frontend.execute(Memory(), trace, channels=2, max_cycles=2)
