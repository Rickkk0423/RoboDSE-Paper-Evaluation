"""Trace-shaped exploratory DynamicVLA workload, separate from frozen pi05 results.

Target arithmetic is BF16, including source FP32 modules. This is a hardware
mapping assumption, not evidence of policy equivalence. Non-matmul work is omitted.
"""
import math
from types import SimpleNamespace

from .neusim_compute import NeuSimTiming
from .workload import Op


class DynamicVLAWorkload:
    def __init__(self, profile):
        cfg = profile['checkpoint_config']
        self.c = SimpleNamespace(H=cfg['chunk_size'], flow_steps=cfg['num_steps'],
                                 w_bytes=2, dit_layers=1)
        self.prefix = [o for o in profile['operations'] if o['phase'] == 'prefix']
        dit = [o for o in profile['operations'] if o['phase'] == 'dit']
        if not self.prefix or not dit or len(dit) % self.c.flow_steps:
            raise ValueError('Incomplete prefix/denoising trace')
        count = len(dit) // self.c.flow_steps
        self.step = dit[:count]
        if any(dit[i*count:(i+1)*count] != self.step for i in range(self.c.flow_steps)):
            raise ValueError('Denoising operations vary across steps; explicit per-step lowering required')
        if any(o['kind'] == 'conv2d' for o in self.step):
            raise ValueError('DiT convolution batching not implemented')
        if not any(o['kind'] == 'attention_matmul' for o in self.step):
            raise ValueError('Attention trace missing')
        self.kv_total_bytes = profile['kv_cache']['elements'] * 2
        if not self.kv_total_bytes:
            raise ValueError('KV cache trace missing')
        self.kv_layer_bytes = self.kv_total_bytes / len(self.prefix)
        # Conservative full-output working set; no tile-level liveness model.
        self.vlm_act_bytes = max(math.prod(o['output_shape']) for o in self.prefix) * 8
        self.dit_layer_params = sum(o['weight_elements'] for o in self.step)
        self.kernels = {}

    def vlm_ops(self, kv_on_chip, util, act_on_chip=True):
        ops = []
        for i, row in enumerate(self.prefix):
            name = f'dvla_prefix_{i}'
            self.kernels[name] = (row, 1)
            wb = row['weight_elements'] * 2
            kv = 0 if kv_on_chip else self.kv_layer_bytes
            # Full intermediate read/write estimate when the working set spills.
            spill = 0 if act_on_chip else math.prod(row['output_shape']) * 4
            ops.append(Op(name, row['flops'], util, wb + kv + spill, 'vlm', wb))
        return ops

    def dit_round_ops(self, batch, n_steps, kv_on_chip, array_rows, slice_mode, resident_frac):
        ops = []
        attention_count = sum(o['kind'] == 'attention_matmul' for o in self.step)
        for s in range(n_steps):
            for i, row in enumerate(self.step):
                attention = row['kind'] == 'attention_matmul'
                name = f'dvla_dit_s{s}_o{i}_b{batch}' + ('_attn' if attention else '_lin')
                self.kernels[name] = (row, batch)
                wb = row['weight_elements'] * 2 * (1-resident_frac)
                kv = self.kv_total_bytes * batch / attention_count if attention and not kv_on_chip else 0
                util = 1 if slice_mode else min(1, row['m'] * (1 if attention else batch) / array_rows)
                ops.append(Op(name, row['flops']*batch, util, wb+kv, 'dit', wb))
        return ops

    def vlm_totals(self):
        return sum(o['flops'] for o in self.prefix), sum(o['weight_elements']*2 for o in self.prefix)

    def dit_totals_per_request(self):
        return (sum(o['flops'] for o in self.step)*self.c.flow_steps,
                self.dit_layer_params*2*self.c.flow_steps)


class DynamicVLATiming(NeuSimTiming):
    """NeuSim for traced GEMMs; analytical conv floor (no verified conv lowering)."""
    def __call__(self, op, group_name, group_peak, hw):
        row, batch = self.workload.kernels[op.name]
        cores = round(group_peak / hw.core_peak)
        key = (cores, hw.array_rows, hw.freq_hz)
        if hw.slice_mode or hw.array_rows != hw.array_cols:
            raise NotImplementedError('Only unsliced square arrays supported')
        if key not in self.models:
            self.models[key] = self.factory(dict(num_sa=cores, num_vu=cores, sa_dim=hw.array_rows,
                                                 freq_GHz=hw.freq_hz/1e9, use_vu_for_small_matmul=False))
        if row['kind'] == 'conv2d':
            self.fallback_calls += 1
            return op.flops / (group_peak * op.util)
        private = row['kind'] == 'attention_matmul'
        m = row['m'] if private else row['m'] * batch
        repeats = row['repeats'] * (batch if private else 1)
        cache = (key, m, row['n'], row['k'], repeats)
        if cache not in self.op_times:
            self.op_times[cache] = repeats * self.models[key].gemm_ns(m, row['n'], row['k'], 'BFLOAT16') * 1e-9
            self.resolved_calls += 1
        return self.op_times[cache]
