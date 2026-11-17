"""Frozen-backend replay with an independently built, real-cycle C++ issue loop."""
import ctypes as ct
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np

from channel_frontend import partition_address


class Result(ct.Structure):
    _fields_ = [('accepted', ct.c_uint64), ('completed', ct.c_uint64),
                ('cycles', ct.c_uint64), ('rejected', ct.c_uint64),
                ('counts', ct.c_uint64*2), ('first_offer', ct.c_double*2),
                ('first_done', ct.c_double*2), ('last_done', ct.c_double*2)]


def build(out):
    source = Path(__file__).with_name('v5_driver.cpp')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    library = out / ('v5_driver.dylib' if sys.platform == 'darwin' else 'v5_driver.so')
    subprocess.run(['c++', '-O2', '-std=c++17', '-shared', '-fPIC', str(source),
                    '-o', str(library), *([] if sys.platform == 'darwin' else ['-ldl'])], check=True)
    return library


def execute(memories, trace, *, channels, issue_width, driver, library,
            bg_geometry=None, outstanding=512, max_cycles=200_000_000):
    if not isinstance(memories, list):
        memories = [memories]
    with np.load(trace) as data:
        issue = np.ascontiguousarray(np.repeat(data['issue_ns'], 2), dtype=np.float64)
        core = np.ascontiguousarray(np.repeat(data['core'], 2), dtype=np.uint8)
        address = np.ascontiguousarray(np.repeat(data['address'], 2) +
            np.tile(np.array([0,32], dtype=np.uint64), len(data['core'])), dtype=np.uint64)
        write = np.ascontiguousarray(np.repeat(data['write'], 2), dtype=np.uint8)
        epoch = np.ascontiguousarray(np.repeat(data['epoch'],2) if 'epoch' in data.files
                                    else np.zeros(len(issue)),dtype=np.uint32)
        if bg_geometry is not None:
            owner = np.repeat(data['owner'], 2) if 'owner' in data.files else core
            address = np.ascontiguousarray(partition_address(address//32,
                owner.astype(np.uint64), channels, 32, mop_geometry=bg_geometry), dtype=np.uint64)
    if not np.isfinite(issue).all() or np.any(issue < 0) or np.any(np.diff(issue) < 0):
        raise ValueError('invalid timed input')
    if any(m.tx_bytes != 32 or m.tck_ns != memories[0].tck_ns for m in memories):
        raise ValueError('driver requires equal native32 geometry')
    capacity = memories[0].capacity_bytes * (channels if len(memories) > 1 else 1)
    if int(address.max())+32 > capacity:
        raise ValueError('replay exceeds physical capacity')
    lib = ct.CDLL(str(driver))
    lib.v5_error.restype = ct.c_char_p
    array = np.ctypeslib.ndpointer
    lib.v5_execute.argtypes = [ct.c_char_p, ct.POINTER(ct.c_void_p), ct.c_int, ct.c_int,
        ct.c_int, ct.c_int, ct.c_uint64, ct.c_double, ct.c_uint64,
        array(dtype=np.float64, flags='C_CONTIGUOUS'), array(dtype=np.uint8, flags='C_CONTIGUOUS'),
        array(dtype=np.uint64, flags='C_CONTIGUOUS'), array(dtype=np.uint8, flags='C_CONTIGUOUS'),
        array(dtype=np.uint32, flags='C_CONTIGUOUS'),
        ct.POINTER(Result)]
    lib.v5_execute.restype = ct.c_int
    result = Result()
    handles = (ct.c_void_p*len(memories))(*(m.handle for m in memories))
    status = lib.v5_execute(str(library).encode(), handles, len(memories), channels, issue_width,
        outstanding, max_cycles, memories[0].tck_ns, len(issue), issue, core, address, write, epoch, ct.byref(result))
    if status < 0:
        raise RuntimeError(lib.v5_error().decode())
    if list(result.counts) != [int(np.count_nonzero(core == c)) for c in (0,1)]:
        raise RuntimeError('offered/completed per-stream accounting mismatch')
    nullable = lambda values: [float(v) if v >= 0 else None for v in values]
    return dict(accepted=result.accepted, completed=result.completed,
        stream_transactions=list(result.counts), cycles=result.cycles, tck_ns=memories[0].tck_ns,
        logical_bytes=result.accepted*32, first_offer_ns=nullable(result.first_offer),
        first_completion_ns=nullable(result.first_done), last_completion_ns=nullable(result.last_done),
        rejected_attempts=result.rejected,
        mapped_transactions_sha256=hashlib.sha256(address.tobytes()+core.tobytes()).hexdigest(),
        frontend_version='v5-real-cycle-channel-fifo-rr', issue_width=issue_width, outstanding=outstanding)
