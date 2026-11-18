"""Isolated fixed-input inference probe; no robot episodes or shared service calls."""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--eai-root', type=Path, required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run under a dedicated Slurm allocation')
    a.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(a.eai_root / 'src'))
    import torch
    from torch.utils._python_dispatch import TorchDispatchMode
    from eai.integrations.dynamicvla.worker import build_context, _build_model_runner
    torch.set_num_threads(int(os.environ.get('SLURM_CPUS_PER_TASK', '2')))
    context = build_context(a.config)
    runner = _build_model_runner(context)
    model = runner.load()
    device = next(model.parameters()).device
    if device.type != 'cuda':
        raise RuntimeError('GPU allocation required for this timing probe')
    torch.manual_seed(20261118)
    batch = {'observation.state': torch.zeros(1, 2, 6, device=device),
             'task': ['pick up the object']}
    for key, feature in model.config.image_features.items():
        batch[key] = torch.rand(1, 2, *feature.shape, device=device)
    noise = torch.randn(1, 20, 32, device=device)
    phase = ['other']
    phase_times = []
    trace = []
    capturing = [False]
    linear_depth = [0]
    kv_info = {}
    dispatched = Counter()

    def tensors(value):
        if isinstance(value, torch.Tensor):
            return [value]
        if isinstance(value, dict):
            return sum((tensors(v) for v in value.values()), [])
        if isinstance(value, (list, tuple)):
            return sum((tensors(v) for v in value), [])
        return []

    def wrap(name, label):
        original = getattr(model.model, name)
        def call(*args, **kwargs):
            previous = phase[0]
            phase[0] = label
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            start.record()
            result = original(*args, **kwargs)
            end.record()
            phase_times.append((label, start, end))
            if label == 'prefix':
                ts = tensors(result[1])
                kv_info.update(prefix_tokens=int(result[0].shape[-1]),
                               shapes=[list(t.shape) for t in ts],
                               elements=sum(t.numel() for t in ts),
                               runtime_bytes=sum(t.numel()*t.element_size() for t in ts))
            phase[0] = previous
            return result
        setattr(model.model, name, call)

    wrap('sample_vlm_embedding', 'prefix')
    wrap('denoise_step', 'dit')
    handles = []
    def pre(module, args):
        linear_depth[0] += 1
    def hook(name):
        def record(module, args, output):
            if capturing[0]:
                x = args[0]
                if isinstance(module, torch.nn.Linear):
                    m, n, k = x.numel() // x.shape[-1], module.out_features, module.in_features
                    repeats = 1
                    kind = 'linear'
                else:
                    m = output.shape[0] * output.shape[-2] * output.shape[-1]
                    n = module.out_channels // module.groups
                    k = module.in_channels // module.groups * math.prod(module.kernel_size)
                    repeats = module.groups
                    kind = 'conv2d'
                trace.append(dict(phase=phase[0], kind=kind, name=name, m=m, n=n, k=k,
                                  repeats=repeats, flops=2*m*n*k*repeats,
                                  weight_elements=module.weight.numel(),
                                  weight_bytes=module.weight.numel()*module.weight.element_size(),
                                  input_dtype=str(x.dtype), weight_dtype=str(module.weight.dtype),
                                  output_shape=list(output.shape)))
            linear_depth[0] -= 1
        return record
    for name, module in model.named_modules():
        if isinstance(module, (torch.nn.Linear, torch.nn.Conv2d)):
            handles.extend([module.register_forward_pre_hook(pre), module.register_forward_hook(hook(name))])

    class Matmuls(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            result = func(*args, **(kwargs or {}))
            dispatched[str(func)] += 1
            if capturing[0] and not linear_depth[0]:
                if func in (torch.ops.aten.mm.default, torch.ops.aten.bmm.default, torch.ops.aten.matmul.default):
                    x, y = args[:2]
                    m, k, n = x.shape[-2], x.shape[-1], y.shape[-1]
                    repeats = math.prod(result.shape[:-2])
                    trace.append(dict(phase=phase[0], kind='attention_matmul', name=str(func),
                                      m=m, n=n, k=k, repeats=repeats, flops=2*m*n*k*repeats,
                                      weight_elements=0, weight_bytes=0, input_dtype=str(x.dtype),
                                      output_shape=list(result.shape)))
                elif 'scaled_dot_product' in str(func):
                    raise RuntimeError('Fused attention requires explicit trace lowering: '+str(func))
            return result

    def invoke():
        # sample_actions mutates supplied noise in-place.
        return model.predict_action_chunk(batch, noise=noise.clone())
    with torch.inference_mode():
        for _ in range(2):
            invoke()
        torch.cuda.synchronize()
        phase_times.clear()
        timings = []
        outputs = []
        for _ in range(5):
            torch.cuda.synchronize()
            start = time.perf_counter()
            output = invoke()
            torch.cuda.synchronize()
            timings.append((time.perf_counter()-start)*1000)
            outputs.append(output.detach().cpu())
        measured_phase_ms = [(label, start.elapsed_time(end)) for label, start, end in phase_times]
        capturing[0] = True
        with Matmuls():
            traced_output = invoke()
        torch.cuda.synchronize()
        capturing[0] = False
    for handle in handles:
        handle.remove()
    checkpoint = context.artifact.canonical_path / 'model.safetensors'
    digest = hashlib.sha256()
    with checkpoint.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    sha = digest.hexdigest()
    source_files = [Path(__file__), a.eai_root/'src/eai/integrations/dynamicvla/worker.py',
                    context.source.source_root/'policies/dynamicvla/modeling_dynamicvla.py']
    result = dict(schema=1, host=socket.gethostname(), slurm_job=os.environ['SLURM_JOB_ID'],
                  gpu=torch.cuda.get_device_name(), torch_version=torch.__version__,
                  checkpoint_sha256=sha, checkpoint_config=json.loads((checkpoint.parent/'config.json').read_text()),
                  source_sha256={str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files},
                  parameter_elements=sum(v.numel() for v in model.parameters()),
                  parameter_bytes=sum(v.numel()*v.element_size() for v in model.parameters()),
                  parameter_dtypes=dict(Counter(str(v.dtype) for v in model.parameters())),
                  kv_cache=kv_info, inference_ms=timings, phase_ms=measured_phase_ms,
                  output_shape=list(outputs[0].shape), output_finite=bool(torch.isfinite(outputs[0]).all()),
                  repeat_max_abs_error=max(float((o-outputs[0]).abs().max()) for o in outputs),
                  trace_max_abs_error=float((traced_output.cpu()-outputs[0]).abs().max()),
                  peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(), operations=trace,
                  dispatched_operations=dict(dispatched), final_hook_depth=linear_depth[0],
                  scope='One synthetic input, B=1, two cameras/history=2, short prompt; not task episodes. '
                        'Linear/Conv2d module operations plus explicit non-module mm/bmm. '
                        'Elementwise, normalization, softmax and data movement not lowered to NPU compute. '
                        'Timings include lightweight hooks and CUDA event instrumentation.')
    (a.out/'profile.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('operations','checkpoint_config','source_sha256')}, indent=2))


if __name__ == '__main__':
    main()
