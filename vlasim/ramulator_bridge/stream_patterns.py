"""Exact-count offered stream patterns and pre-execution trace descriptors."""
import random


def uniform_order(a_count, b_count):
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in (a_count, b_count)):
        raise ValueError("stream counts must be nonnegative integers")
    total = a_count + b_count
    if not total:
        raise ValueError("empty stream pair")
    accumulator = 0
    for _ in range(total):
        accumulator += a_count
        if accumulator >= total:
            yield 0
            accumulator -= total
        else:
            yield 1


def skew_order(total, epochs):
    if total <= 0 or epochs <= 0 or total % (2 * epochs):
        raise ValueError("traffic must divide into complete paired skew windows")
    half = total // (2 * epochs)
    a_first = half * 40 // 100
    for _ in range(epochs):
        yield from uniform_order(a_first, half - a_first)
        yield from uniform_order(half - a_first, a_first)


def shuffled_order(total, seed):
    if total <= 0 or total % 2:
        raise ValueError("shuffle requires positive even traffic")
    order = [0] * (total // 2) + [1] * (total // 2)
    random.Random(seed).shuffle(order)
    yield from order


def describe_order(order):
    counts = [0, 0]
    switches = run = longest = total = abs_skew_sum = max_skew = 0
    near = {1024: 0, 4096: 0, 65536: 0}
    previous = None
    for stream in order:
        if stream not in (0, 1):
            raise ValueError("expected stream 0 or 1")
        if previous is not None and stream != previous:
            switches += 1
            run = 0
        run += 1
        longest = max(longest, run)
        previous = stream
        counts[stream] += 1
        total += 1
        skew = abs(counts[0] - counts[1]) * 64
        abs_skew_sum += skew
        max_skew = max(max_skew, skew)
        for limit in near:
            near[limit] += skew <= limit
    if not total:
        raise ValueError("empty order")
    return {"requests": total, "stream_requests": counts,
            "actual_vlm_ratio_pct": 100 * counts[0] / total,
            "switch_fraction": switches / max(total - 1, 1),
            "mean_run_lines": total / (switches + 1), "max_run_lines": longest,
            "max_cursor_skew_bytes": max_skew,
            "mean_abs_cursor_skew_bytes": abs_skew_sum / total,
            "near_cursor_fraction": {str(k): v / total for k, v in near.items()},
            "descriptor_scope": "Offered logical-request order only. Cursor skew ignores base phase and is not a decoded bank conflict or accepted-queue measurement."}


def experiment_cases():
    cases = []
    for shift in (0, 4096):
        for ratio in (4000, 4500, 4800, 4900, 4950, 4990, 5000, 5010, 5050, 5100, 5200, 5500, 6000):
            cases.append(dict(shift_bytes=shift, ratio_bp=ratio, size_mib=4,
                              pattern="uniform", parameter=0, group="dense_ratio"))
        for ratio in (4990, 5000, 5010):
            cases.append(dict(shift_bytes=shift, ratio_bp=ratio, size_mib=16,
                              pattern="uniform", parameter=0, group="size_transfer"))
        for epochs in (1, 16, 256):
            cases.append(dict(shift_bytes=shift, ratio_bp=5000, size_mib=4,
                              pattern="skew", parameter=epochs, group="fixed_global_ratio"))
        for seed in (17, 29):
            cases.append(dict(shift_bytes=shift, ratio_bp=5000, size_mib=4,
                              pattern="shuffle", parameter=seed, group="fixed_global_ratio"))
        for ratio in (4900, 5000, 5100):
            cases.append(dict(shift_bytes=shift, ratio_bp=ratio, size_mib=4,
                              pattern="legacy", parameter=0, group="generator_control"))
    for case in cases:
        case["case"] = (f"{case['pattern']}{case['parameter']}_bp{case['ratio_bp']}"
                        f"_shift{case['shift_bytes']}_{case['size_mib']}MiB")
    return cases
