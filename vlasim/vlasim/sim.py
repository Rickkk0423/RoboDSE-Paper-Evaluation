"""Request-level discrete-event simulator for VLA inference on a multi-core NPU.

Execution organisations supported
---------------------------------
* serial     : one request at a time; VLM and DiT each use ALL cores (latency-oriented baseline).
* pipelined  : VLM group and DiT group run concurrently on disjoint cores (decoupled hand-off).
    - dit_stages = 1 : DiT processes each request's full flow schedule (plain VLM/DiT overlap).
    - dit_stages = k : flow steps split into k contiguous stages; one request per stage.
                       Each DiT round advances every in-flight request by one stage, executing
                       same-layer shared-weight linears as ONE batched GEMM (weights fetched once)
                       and attention privately per request.  dit_batching=False is the ablation
                       where stages run back-to-back with separate weight fetches.

Shared DRAM is modelled as a fluid resource (see dram.py); each core group executes one op at a
time, op progress rate = min(compute rate, allocated bandwidth / op bytes).

Timing outputs: per-request L = adoption-available time - observation time (VLM start in
jit/eager, r*T in periodic), and S = interval between successive in-order completions.
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, field
import numpy as np

from .workload import Pi05Workload, Op
from .hw import HWConfig, MapConfig
from .dram import DRAMModel

INF = float("inf")


def split_steps(n: int, k: int) -> list[int]:
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


@dataclass
class Group:
    name: str
    peak: float
    ops: deque = field(default_factory=deque)
    cur: Op | None = None
    rem: float = 0.0          # remaining fraction of current op
    busy: float = 0.0         # accumulated busy time

    def load_next(self) -> bool:
        if self.ops:
            self.cur, self.rem = self.ops.popleft(), 1.0
            return True
        self.cur = None
        return False


class Simulator:
    def __init__(self, hw: HWConfig, mp: MapConfig, wl: Pi05Workload | None = None,
                 dram: DRAMModel | None = None, compute_time_fn=None):
        """compute_time_fn(op, group_name, group_peak, hw) -> seconds of pure compute.
        Hook for NeuSim (or RTL-calibrated) per-op costs; default = flops / (util * peak)."""
        self.hw, self.mp = hw, mp
        self.compute_time_fn = compute_time_fn
        self.wl = wl or Pi05Workload()
        self.dram = dram or DRAMModel()
        c = self.wl.c
        k = mp.dit_stages if mp.mode == "pipelined" else 1
        if mp.mode not in ("serial", "pipelined"):
            raise ValueError("unknown execution mode")
        if not 1 <= k <= c.flow_steps:
            raise ValueError("dit_stages must be between 1 and flow_steps")
        if mp.vlm_queue_max < 1 or mp.max_wait < 0:
            raise ValueError("queue capacity must be positive and max_wait nonnegative")
        if mp.stream_partition is not None and not 0 < mp.stream_partition < 1:
            raise ValueError("stream_partition must lie strictly between zero and one")
        if mp.vlm_launch not in ("jit", "eager", "periodic"):
            raise ValueError("unknown VLM launch mode")
        if mp.vlm_launch == "periodic" and (mp.launch_period_s is None
                or not math.isfinite(mp.launch_period_s) or mp.launch_period_s <= 0):
            raise ValueError("periodic launch requires a finite positive launch_period_s")
        if mp.jit_freeze_after is not None and (isinstance(mp.jit_freeze_after, bool)
                or not isinstance(mp.jit_freeze_after, int) or mp.jit_freeze_after < 1):
            raise ValueError("jit_freeze_after must be a positive integer")
        self.k = k
        self.stage_steps = split_steps(c.flow_steps, k)
        # --- SRAM decisions ---
        # private per-core SRAM: must hold one double-buffered tile pass (feasibility only;
        # its effect on op time is NeuSim's job via compute_time_fn)
        self.local_ok = hw.local_kb >= hw.local_min_kb
        # shared SRAM, filled in priority order: DiT residency -> VLM activation working set -> prefix KV
        dit_w_total = self.wl.dit_layer_params * c.w_bytes * c.dit_layers
        sram = hw.sram_mb * 1e6
        resident = min(mp.dit_resident_mb * 1e6, sram, dit_w_total)
        free = sram - resident
        self.act_on_chip = free >= self.wl.vlm_act_bytes
        if self.act_on_chip:
            free -= self.wl.vlm_act_bytes
        live_kv = (k + mp.vlm_queue_max + 1) if mp.mode == "pipelined" else 1
        kv_need = self.wl.kv_total_bytes * live_kv
        if mp.kv_on_chip is None:
            self.kv_on_chip = free >= kv_need
        else:
            self.kv_on_chip = mp.kv_on_chip
        self.resident_frac = resident / dit_w_total if dit_w_total else 0.0
        used = resident + (self.wl.vlm_act_bytes if self.act_on_chip else 0) \
            + (kv_need if self.kv_on_chip else 0)
        self.sram_ok = used <= sram + 1e-6 and self.local_ok
        # --- core groups ---
        if mp.mode == "serial":
            pv = pd = hw.peak
        else:
            assert 0 < mp.vlm_cores < hw.n_cores, "pipelined mode needs cores for both groups"
            pv = mp.vlm_cores * hw.core_peak
            pd = (hw.n_cores - mp.vlm_cores) * hw.core_peak
        self.g = {"vlm": Group("vlm", pv), "dit": Group("dit", pd)}
        self._queued_costs = {}

    # ------------------------------------------------------------------ helpers
    def _rates(self, diagnostics=None) -> dict[str, float]:
        """progress rate (fraction/s) of each group's current op under fluid DRAM sharing."""
        tc, demand = {}, {}
        for n, g in self.g.items():
            if g.cur is None:
                continue
            op = g.cur
            if self.compute_time_fn is not None:
                tc[n] = self.compute_time_fn(op, n, g.peak, self.hw)
            else:
                eff = op.flops / max(op.util, 1e-9)
                tc[n] = eff / g.peak if eff > 0 else 0.0
            if op.dram_bytes <= 0:
                demand[n] = 0.0
            else:
                demand[n] = op.dram_bytes / tc[n] if tc[n] > 0 else INF
        dem = {"vlm": demand.get("vlm", 0.0), "dit": demand.get("dit", 0.0)}
        # replace INF with peak so water-filling works
        dem = {k: (self.hw.dram_bw if v == INF else v) for k, v in dem.items()}
        targets = None
        if self.mp.bw_policy == "balance" and self.mp.stream_partition is None:
            targets = self.dram.balance_targets(self.hw.dram_bw, self._remaining())
        if self.mp.stream_partition is not None and self.mp.mode == "pipelined":
            p = self.mp.stream_partition
            alloc = {n: min(dem[n], self.hw.dram_bw * self.dram.eta_seq * share)
                     for n, share in (("vlm", p), ("dit", 1 - p))}
        else:
            alloc = self.dram.allocate(self.hw.dram_bw, dem, self.mp.bw_policy, targets)
        rates = {}
        for n, g in self.g.items():
            if g.cur is None:
                continue
            op = g.cur
            r_c = 1.0 / tc[n] if tc[n] > 0 else INF
            r_m = alloc[n] / op.dram_bytes if op.dram_bytes > 0 else INF
            r = min(r_c, r_m)
            rates[n] = r if r < INF else 1e12
            if diagnostics is not None:
                diagnostics[n] = tc[n]
        return rates

    def _remaining(self) -> dict[str, tuple[float, float]]:
        """(compute_time_left, dram_bytes_left) of each group's current unit of work.
        This is the 'progress estimate' a progress-aware memory controller would need."""
        out = {}
        for n, g in self.g.items():
            if g.cur is None:
                out[n] = (0.0, 0.0); continue
            def cost(o):
                return (self.compute_time_fn(o, n, g.peak, self.hw)
                        if self.compute_time_fn is not None
                        else o.flops / max(o.util, 1e-9) / g.peak)
            cached = self._queued_costs.get(n)
            if cached is None or cached[0] is not g.ops:
                # A work unit gets a fresh deque; within it only popleft is used.
                suffix = [(0.0, 0.0)]
                for op in reversed(g.ops):
                    c, b = suffix[-1]
                    suffix.append((c + cost(op), b + op.dram_bytes))
                cached = (g.ops, suffix)
                self._queued_costs[n] = cached
            c, b = cached[1][len(g.ops)]
            c += g.rem * cost(g.cur)
            b += g.rem * g.cur.dram_bytes
            out[n] = (c, b)
        return out

    def _vlm_ops(self):
        return deque(self.wl.vlm_ops(self.kv_on_chip, self.mp.vlm_util, self.act_on_chip))

    def _dit_round_ops(self, stage_reqs: list):
        """stage_reqs[s] = request id or None for stage s."""
        c, hw = self.wl.c, self.hw
        ops = deque()
        if self.k == 1 or self.mp.dit_batching:
            nmax = max(self.stage_steps[s] for s, r in enumerate(stage_reqs) if r is not None)
            for j in range(nmax):
                b = sum(1 for s, r in enumerate(stage_reqs)
                        if r is not None and self.stage_steps[s] > j)
                step_ops = self.wl.dit_round_ops(b, 1, self.kv_on_chip, hw.array_rows,
                                                hw.slice_mode, self.resident_frac)
                request_ids = tuple(r for s, r in enumerate(stage_reqs)
                                    if r is not None and self.stage_steps[s] > j)
                for op in step_ops:
                    op.request_ids = request_ids
                ops.extend(step_ops)
        else:  # split without batching: each stage fetches weights separately
            for s, r in enumerate(stage_reqs):
                if r is None:
                    continue
                stage_ops = self.wl.dit_round_ops(1, self.stage_steps[s], self.kv_on_chip,
                                                hw.array_rows, hw.slice_mode, self.resident_frac)
                for op in stage_ops:
                    op.request_ids = (r,)
                ops.extend(stage_ops)
        return ops

    # ------------------------------------------------------------------ main loop
    def run(self, n_requests: int = 40, warmup: int = 8, record: bool = False,
            diagnostics: bool = False) -> dict:
        """record=True returns `timeline`: (t_start, t_end, group, op_name, dram_bytes, request_ids)
        for every op, plus `memory_segments` at each fluid-rate event for native replay.
        diagnostics=True adds rounds, all request timestamps, observation queue statistics,
        and predictor state. Queue means are time-weighted over measurement_window_s;
        queue maxima include the instantaneous arrival before dispatch. Tail drain rounds
        are explicitly marked and the existing k+2 completion cooldown is retained.
        Periodic mode has no ready-queue backpressure or timeout; SRAM feasibility remains
        the configured static allocation check, not validation of an overloaded queue's KV.
        """
        mp, k = self.mp, self.k
        periodic = mp.vlm_launch == "periodic"
        if warmup < 0 or n_requests - warmup - (k + 2) < 2:
            raise ValueError("need at least two steady-state requests after warmup and drain")
        for g in self.g.values():
            g.ops.clear()
            g.cur, g.rem, g.busy = None, 0.0, 0.0
        t = 0.0
        obs, done = {}, {}
        next_id = 0
        vlm_req = None
        ready = deque()                 # VLM-finished requests waiting for DiT stage 0
        slots = [None] * k              # request in each DiT stage (between rounds)
        round_reqs = None               # stage assignment of the round in progress
        wait_deadline = None            # bounded-wait deadline for an under-filled round
        bytes_acc = {"vlm": 0.0, "dit": 0.0}
        gv, gd = self.g["vlm"], self.g["dit"]
        vlm_start = round_start = None
        last_vlm_dur = last_round_dur = None
        vlm_wake = None                 # jit launch: earliest time VLM may start
        timeline, op_t0 = [], {}
        memory_segments = []
        rounds, round_stats = [], None
        previous_round_end = 0.0
        pending = deque()               # observations waiting for the VLM group; never dropped
        next_obs = 0
        requests, queue_events = {}, [(0.0, 0)]
        samples = {"vlm": [], "round": []}
        frozen = {"vlm": None, "round": None}

        def update_predictor(name, value):
            if mp.jit_freeze_after is not None and frozen[name] is None:
                samples[name].append(value)
                if len(samples[name]) == mp.jit_freeze_after:
                    frozen[name] = sum(samples[name]) / len(samples[name])

        def queue_changed():
            if diagnostics:
                queue_events.append((t, len(pending)))

        def started(n):                 # call right after a successful load_next()
            op_t0[n] = t

        def finished(n, g, reqs):
            if record:
                timeline.append((op_t0[n], t, n, g.cur.name, g.cur.dram_bytes,
                                 g.cur.request_ids or reqs))

        def in_system():
            return (vlm_req is not None) or ready or any(s is not None for s in slots) \
                   or (round_reqs is not None)

        while len(done) < n_requests:
            if periodic:
                while next_obs < n_requests and next_obs * mp.launch_period_s <= t:
                    obs[next_obs] = next_obs * mp.launch_period_s
                    pending.append(next_obs)
                    next_obs += 1
                    queue_changed()
            # ---------------- scheduling decisions ----------------
            progressed = True
            while progressed:
                progressed = False
                # VLM launch
                if gv.cur is None and vlm_req is None and next_id < n_requests:
                    can = (bool(pending) if periodic else len(ready) < mp.vlm_queue_max) \
                        if mp.mode == "pipelined" else (not in_system())
                    if periodic:
                        can = can and bool(pending)
                    if can and mp.mode == "pipelined" and mp.vlm_launch == "jit" \
                            and last_vlm_dur is not None and last_round_dur is not None:
                        # predicted time DiT can accept a new stage-0 request
                        predicted_round = frozen["round"] if frozen["round"] is not None else last_round_dur
                        predicted_vlm = frozen["vlm"] if frozen["vlm"] is not None else last_vlm_dur
                        free = (round_start + predicted_round) if round_reqs is not None else t
                        earliest = free - predicted_vlm
                        if t < earliest - 1e-9:
                            vlm_wake, can = earliest, False
                        else:
                            vlm_wake = None
                    if can and (mp.mode == "pipelined" or gd.cur is None):
                        vlm_start = t
                        vlm_req = pending.popleft() if periodic else next_id
                        next_id += 1
                        if periodic:
                            queue_changed()
                        else:
                            obs[vlm_req] = t
                        if diagnostics:
                            requests[vlm_req] = dict(request_id=vlm_req, obs_s=obs[vlm_req],
                                                    vlm_start_s=t)
                        gv.ops = self._vlm_ops(); gv.load_next(); started("vlm")
                        progressed = True
                # DiT round launch
                if gd.cur is None and round_reqs is None:
                    occupied = any(s is not None for s in slots[1:]) if k > 1 else False
                    start = False
                    if ready:
                        slots[0] = ready.popleft(); start = True
                    elif occupied:
                        incoming = (vlm_req is not None) or (next_id < n_requests)
                        if not incoming:
                            start = True            # drain: nobody will join
                        elif not periodic:
                            if wait_deadline is None:
                                wait_deadline = t + mp.max_wait
                            if t >= wait_deadline - 1e-12:
                                start = True        # singleton fallback
                    if start:
                        wait_deadline = None
                        round_start = t
                        round_reqs = list(slots)
                        if diagnostics:
                            round_stats = dict(start_s=t, stage_request_ids=list(slots),
                                               tail_drain=periodic and not ready and slots[0] is None,
                                               compute_s=0.0, exposed_memory_s=0.0,
                                               linear_s=0.0, attention_s=0.0,
                                               dram_bytes=0.0, weight_bytes=0.0,
                                               wait_before_s=t - previous_round_end)
                        gd.ops = self._dit_round_ops(round_reqs); gd.load_next(); started("dit")
                        progressed = True

            # ---------------- advance time ----------------
            compute_times = {} if diagnostics else None
            rates = self._rates(compute_times)
            dt = INF
            for n, g in self.g.items():
                if g.cur is not None and rates[n] > 0:   # rate 0 = starved by priority
                    dt = min(dt, g.rem / rates[n])
            if wait_deadline is not None and gd.cur is None:
                dt = min(dt, max(wait_deadline - t, 0.0))
            if vlm_wake is not None and gv.cur is None and vlm_wake > t:
                dt = min(dt, vlm_wake - t)
            if periodic and next_obs < n_requests:
                dt = min(dt, max(0.0, next_obs * mp.launch_period_s - t))
            if dt == INF:
                raise RuntimeError("deadlock: nothing to do")
            for n, g in self.g.items():
                if g.cur is not None:
                    frac = min(g.rem, rates[n] * dt)
                    if record:
                        reqs = (vlm_req,) if n == "vlm" else tuple(
                            r for r in round_reqs if r is not None)
                        memory_segments.append(dict(
                            start_s=t, end_s=t + dt, group=n, op_name=g.cur.name,
                            request_ids=g.cur.request_ids or reqs,
                            dram_bytes=frac * g.cur.dram_bytes,
                            weight_bytes=frac * g.cur.weight_bytes,
                            op_fraction_start=1.0 - g.rem,
                            op_fraction_end=1.0 - (g.rem - frac),
                            op_total_dram_bytes=g.cur.dram_bytes))
                    bytes_acc[n] += frac * g.cur.dram_bytes
                    g.rem -= frac
                    g.busy += dt
                    if diagnostics and n == "dit":
                        compute = frac * compute_times[n]
                        round_stats["compute_s"] += compute
                        round_stats["exposed_memory_s"] += max(0.0, dt - compute)
                        kind = "attention_s" if g.cur.name.endswith("_attn") else "linear_s"
                        round_stats[kind] += dt
                        round_stats["dram_bytes"] += frac * g.cur.dram_bytes
                        round_stats["weight_bytes"] += frac * g.cur.weight_bytes
            t += dt
            # ---------------- completions ----------------
            if gv.cur is not None and gv.rem <= 1e-12:
                finished("vlm", gv, (vlm_req,))
                if gv.load_next():
                    started("vlm")
                else:
                    ready.append(vlm_req); vlm_req = None
                    last_vlm_dur = t - vlm_start
                    update_predictor("vlm", last_vlm_dur)
                    if diagnostics:
                        requests[ready[-1]]["vlm_end_s"] = t
            if gd.cur is not None and gd.rem <= 1e-12:
                finished("dit", gd, tuple(r for r in round_reqs if r is not None))
                if gd.load_next():
                    started("dit")
                else:
                    last_round_dur = t - round_start
                    update_predictor("round", last_round_dur)
                    if diagnostics:
                        round_stats.update(end_s=t, duration_s=last_round_dur)
                        rounds.append(round_stats)
                        previous_round_end = t
                    last = round_reqs[-1]
                    if last is not None:
                        done[last] = t
                    slots = [None] + round_reqs[:-1]
                    round_reqs = None

        cooldown = k + 2                # drop pipeline-drain completions (no incoming requests)
        ids = sorted(done)[warmup:len(done) - cooldown]
        L = np.array([done[i] - obs[i] for i in ids])
        comp = np.array([done[i] for i in ids])
        S = np.diff(comp)
        n_meas = len(done)
        extra = {}
        if diagnostics:
            for i, row in requests.items():
                row.update(done_s=done[i], L_s=done[i] - obs[i],
                           S_s=done[i] - done[i - 1] if i else None,
                           vlm_wait_s=row["vlm_start_s"] - obs[i],
                           steady_state=i in ids)
            lo, hi = comp[0], comp[-1]
            intervals = [(a, b, q) for (a, q), (b, _) in
                         zip(queue_events, queue_events[1:] + [(t, 0)])]
            steady_intervals = [(max(a, lo), min(b, hi), q) for a, b, q in intervals
                                if min(b, hi) > max(a, lo)]
            steady_events = [q for a, q in queue_events if lo <= a <= hi]
            extra = dict(requests=[requests[i] for i in sorted(requests)],
                         vlm_queue=dict(events=queue_events,
                             max_length=max(q for _, q in queue_events),
                             steady_max_length=max([q for _, _, q in steady_intervals]
                                                   + steady_events + [0]),
                             steady_mean_length=sum((b-a)*q for a, b, q in steady_intervals)/(hi-lo),
                             measurement_window_s=[lo, hi]),
                         jit_predictor=dict(enabled=mp.vlm_launch == "jit",
                             freeze_after=mp.jit_freeze_after,
                             frozen=all(v is not None for v in frozen.values()),
                             vlm_frozen=frozen["vlm"] is not None,
                             round_frozen=frozen["round"] is not None,
                             vlm_reference_s=frozen["vlm"] if frozen["vlm"] is not None else last_vlm_dur,
                             round_reference_s=frozen["round"] if frozen["round"] is not None else last_round_dur,
                             sample_counts={n: len(v) for n, v in samples.items()}),
                         launch_mode=mp.vlm_launch, launch_period_s=mp.launch_period_s)
        return {
            "L_mean": L.mean(), "L_std": L.std(), "L_p50": np.percentile(L, 50),
            "L_p95": np.percentile(L, 95), "L_max": L.max(),
            "S_mean": S.mean(), "S_std": S.std(), "S_p50": np.percentile(S, 50),
            "S_p95": np.percentile(S, 95), "S_max": S.max(),
            # per-request timeline (observation time, chunk-available time), steady-state only;
            # downstream tools (closed-loop replay, action-age traces) consume this, not just means
            "trace": [(obs[i], done[i]) for i in ids],
            "dram_GB_per_req": (bytes_acc["vlm"] + bytes_acc["dit"]) / n_meas / 1e9,
            "dit_GB_per_req": bytes_acc["dit"] / n_meas / 1e9,
            "vlm_busy": gv.busy / t, "dit_busy": gd.busy / t,
            "kv_on_chip": self.kv_on_chip, "act_on_chip": self.act_on_chip, "sram_ok": self.sram_ok,
            "dram_version": self.dram.version,
            **({"timeline": timeline, "memory_segments": memory_segments} if record else {}),
            **({"dit_rounds": rounds, "makespan_s": t,
                "measurement_window_s": [comp[0], comp[-1]], **extra} if diagnostics else {}),
        }
