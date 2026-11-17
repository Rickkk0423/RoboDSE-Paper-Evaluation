"""Per-channel FIFO injection with cross-channel nonblocking round-robin issue."""
from collections import deque
import hashlib

import numpy as np

from run_native import requests

VERSION = "per-channel-fifo-rr-v1"


def mop_decode(intra, bits):
    """Pinned MOP4CLXOR mapping, in native transaction units, excluding channel."""
    column = intra & 3
    intra >>= 2
    fields = []
    for width in bits[:-2]:
        fields.append(intra & ((1 << width) - 1))
        intra >>= width
    column |= (intra & ((1 << (bits[-1] - 2)) - 1)) << 2
    row = intra >> (bits[-1] - 2)
    fields.append(row)
    shift = 0
    for i, width in enumerate(bits[:-1]):
        fields[i] ^= (column >> shift) & ((1 << width) - 1)
        shift += width
    return fields + [column]


def mop_encode(fields, bits):
    column = fields[-1]
    raw, shift = [], 0
    for field, width in zip(fields[:-1], bits[:-1]):
        raw.append(field ^ ((column >> shift) & ((1 << width) - 1)))
        shift += width
    intra = raw[-1]
    intra = (intra << (bits[-1] - 2)) | (column >> 2)
    for field, width in reversed(list(zip(raw[:-1], bits[:-2]))):
        intra = (intra << width) | field
    return (intra << 2) | (column & 3)


def channel_for(address, tx_bytes, channels):
    if channels < 1 or channels & (channels - 1):
        raise ValueError("CacheLineInterleave needs power-of-two channels")
    return (address // tx_bytes) & (channels - 1)


def partition_address(index, core, channels, tx_bytes, fraction=None, bg_geometry=None,
                      mop_geometry=None):
    """Encode native transactions; disjoint channel or BG sets, no hash mapping."""
    if fraction is not None:
        count = channels * fraction
        if not count.is_integer() or not 0 < count < channels:
            raise ValueError("partition must assign an integer, nonempty channel set")
        cut = int(count)
        subset = list(range(cut)) if core == 0 else list(range(cut, channels))
        channel = subset[index % len(subset)]
        intra = index // len(subset)
    else:
        channel = index % channels
        intra = index // channels
    if bg_geometry is not None:
        shift, width = bg_geometry
        half = (1 << width) // 2
        low = intra & ((1 << shift) - 1)
        high = intra >> shift
        bg = core * half + high % half
        intra = (((high // half) << width | bg) << shift) | low
    if mop_geometry is not None:
        bits, bg_index = mop_geometry
        width = bits[bg_index]
        shift = 2 + sum(bits[:bg_index])
        half = 1 << (width - 1)
        low, high = intra & ((1 << shift) - 1), intra >> shift
        raw = (((high // half) << width | (high % half)) << shift) | low
        fields = mop_decode(raw, bits)
        fields[bg_index] = core * half + fields[bg_index] % half
        intra = mop_encode(fields, bits)
    return (intra * channels + channel) * tx_bytes


def execute(memory, trace, *, channels, issue_width=8, outstanding=512,
            max_cycles=20_000_000, partition=None, bg_geometry=None, mop_geometry=None):
    if min(issue_width, outstanding, max_cycles) < 1:
        raise ValueError("positive issue and cycle limits required")
    queues = [deque() for _ in range(channels)]
    offered = [0, 0]
    address_hash = hashlib.sha256()
    for issue, core, write, address in requests(trace, memory.tx_bytes, memory.capacity_bytes):
        if partition is not None or bg_geometry is not None or mop_geometry is not None:
            address = partition_address(offered[core], core, channels, memory.tx_bytes,
                                        partition, bg_geometry, mop_geometry)
        if address + memory.tx_bytes > memory.capacity_bytes:
            raise ValueError("remapped address exceeds capacity")
        offered[core] += 1
        channel = channel_for(address, memory.tx_bytes, channels)
        queues[channel].append((issue, core, write, address))
        address_hash.update(f"{issue},{core},{int(write)},{address}\n".encode())
    if not sum(offered):
        raise ValueError("empty trace")
    pending, events, latencies = {}, [], []
    cycle = accepted = rejected = cursor = 0
    stream_counts = [0, 0]
    bypass_cycles = 0
    while any(queues) or pending:
        for rid, when in memory.completions():
            if rid not in pending:
                raise RuntimeError("duplicate or unrecognized callback")
            issued_at, core = pending.pop(rid)
            if when < issued_at:
                raise RuntimeError("completion precedes acceptance")
            events.append((when, core))
            latencies.append((when - issued_at) * memory.tck_ns)
        if not any(queues) and not pending:
            break
        if cycle >= max_cycles:
            raise RuntimeError("cycle budget exhausted")
        blocked = set()
        successes = 0
        accepted_after_rejection = False
        while successes < issue_width and len(pending) < outstanding:
            progress = False
            for _ in range(channels):
                channel = cursor
                cursor = (cursor + 1) % channels
                queue = queues[channel]
                if channel in blocked or not queue or queue[0][0] > cycle * memory.tck_ns + 1e-9:
                    continue
                issue, core, write, address = queue[0]
                if not memory.send(accepted, write, address, core):
                    rejected += 1
                    blocked.add(channel)
                    continue
                queue.popleft()
                pending[accepted] = (cycle, core)
                accepted += 1
                stream_counts[core] += 1
                successes += 1
                progress = True
                accepted_after_rejection |= bool(blocked)
                break
            if not progress:
                break
        bypass_cycles += accepted_after_rejection
        memory.tick()
        cycle += 1
    if accepted != len(events) or stream_counts != offered:
        raise RuntimeError("transaction accounting mismatch")
    times = [t for t, _ in events]
    lo, hi = int(len(times) * .1), int(len(times) * .9)
    duration = (times[hi] - times[lo]) * memory.tck_ns
    if duration <= 0:
        raise ValueError("insufficient completions")
    total_time = cycle * memory.tck_ns
    return dict(accepted=accepted, completed=len(events), rejected_attempts=rejected,
                cycles=cycle, tck_ns=memory.tck_ns, transaction_bytes=memory.tx_bytes,
                logical_bytes=accepted * memory.tx_bytes, stream_transactions=dict(enumerate(stream_counts)),
                makespan_GBps=accepted * memory.tx_bytes / total_time,
                achieved_GBps=(hi - lo) * memory.tx_bytes / duration,
                stream_common_window_GBps={str(core): sum(c == core for _, c in events[lo:hi]) * memory.tx_bytes / duration for core in (0, 1)},
                stream_makespan_GBps={str(core): stream_counts[core] * memory.tx_bytes / total_time for core in (0, 1)},
                completion_time_ns=max(times) * memory.tck_ns,
                measurement_start_ns=times[lo] * memory.tck_ns,
                measurement_end_ns=times[hi] * memory.tck_ns,
                latency_p50_ns=float(np.percentile(latencies, 50)), latency_p95_ns=float(np.percentile(latencies, 95)),
                bypass_cycles=bypass_cycles, frontend_version=VERSION,
                mapped_transactions_sha256=address_hash.hexdigest())
