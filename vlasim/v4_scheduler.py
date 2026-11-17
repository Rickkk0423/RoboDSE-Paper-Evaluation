"""Frozen P0-B scheduler experiments; no Stage B grid or simulator edits."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from scipy.signal import correlate, find_peaks, periodogram
from scipy.stats import t as student_t

from case_v3_main import digest, write_csv, write_json
from vlasim import DRAMModel, HWConfig, MapConfig, Simulator
from vlasim.neusim_compute import NeuSimTiming
from vlasim.workload import Pi05Workload


def strict_groups(values, period=1, tolerance=1e-9):
    """Check every adjacent complete group, not just an FFT-selected peak."""
    a = np.asarray(values, dtype=float)
    count = len(a) // period
    if count < 2:
        return dict(pass_gate=False, max_error_s=None, groups=count)
    groups = a[:count * period].reshape(count, period, -1)
    error = float(np.max(np.abs(np.diff(groups, axis=0))))
    return dict(pass_gate=error <= tolerance, max_error_s=error, groups=count)


def batch_means(values):
    a = np.asarray(values, dtype=float)
    size = max(2, int(math.sqrt(len(a))))
    count = len(a) // size
    if count < 2:
        return dict(mean_s=float(np.mean(a)), ci95_s=None, batches=count)
    means = a[:count * size].reshape(count, size).mean(axis=1)
    half = float(student_t.ppf(.975, count - 1) * means.std(ddof=1) / math.sqrt(count))
    return dict(mean_s=float(means.mean()), ci95_s=[float(means.mean()-half), float(means.mean()+half)],
                batches=count, batch_size=size, discarded_tail=len(a)-count*size,
                interpretation='deterministic_time_series_batch_means_not_independent_experiment_CI')


def series_analysis(values):
    a = np.asarray(values, dtype=float)
    third = max(1, len(a)//3)
    drift = float(abs(a[-third:].mean()-a[:third].mean()) / max(abs(a.mean()), 1e-30))
    freq, power = periodogram(a, detrend='linear')
    centered = a-a.mean()
    ac = correlate(centered, centered, mode='full', method='fft')[len(a)-1:]
    ac = ac/ac[0] if ac[0] > 1e-28 else np.ones_like(ac)
    peaks, _ = find_peaks(ac[1:max(3, len(a)//2)])
    peaks = peaks+1
    candidates = list(range(1, min(65, len(a)//2+1)))
    candidates += [int(p) for p in peaks if ac[p] > .5]
    top = np.argsort(power[1:])[-5:]+1
    candidates += [int(round(1/freq[i])) for i in top if freq[i] > 0]
    exact = next((p for p in sorted(set(candidates)) if 1 <= p <= len(a)//2
                  and strict_groups(a, p)['pass_gate']), None)
    spectral = [dict(period_requests=float(1/freq[i]), power=float(power[i]))
                for i in reversed(top) if freq[i] > 0]
    recurrent = [dict(lag=int(p), correlation=float(ac[p])) for p in peaks if ac[p] > .5]
    category = ('strict_periodic' if exact is not None else 'drifting' if drift >= .005
                else 'quasiperiodic_or_unresolved_bounded')
    return dict(classification=category, strict_period_requests=exact, drift_fraction=drift,
                spectrum=spectral, autocorrelation_peaks=recurrent[:30],
                autocorrelation=[float(x) for x in ac[:min(len(ac), 513)]],
                batch_means=batch_means(a))


def periodic_gate(result, period, k):
    rows = [r for r in result['requests'] if r['steady_state'] and r['S_s'] is not None]
    a = np.array([[r['L_s'], r['S_s']] for r in rows])
    third = max(1, len(a)//3)
    drift = float(abs(a[-third:, 0].mean()-a[:third, 0].mean()) / a[:third, 0].mean())
    relative = float(np.max(np.abs(a[:, 1]/period-1)))
    groups = {str(p): strict_groups(a, p) for p in sorted({1, k})}
    strict = any(g['pass_gate'] for g in groups.values())
    queue = result['vlm_queue']['steady_max_length']
    feasible = drift < .005 and queue <= 1 and relative < 1e-6
    return dict(feasible=bool(feasible), strict_periodic=bool(strict),
                pass_gate=bool(feasible and strict), L_drift_fraction=drift,
                queue_steady_max=queue, S_max_relative_error=relative,
                adjacent_groups=groups, L_mean_s=float(a[:, 0].mean()),
                S_mean_s=float(a[:, 1].mean()), steady_requests=len(rows))


def load_selection(root):
    root = Path(root)
    parent_path = root/'experiment_manifest.json'
    parent = json.loads(parent_path.read_text())
    selected_path = root/'convergence_selected_deep/experiment_manifest.json'
    selected_manifest = json.loads(selected_path.read_text())
    if digest(parent_path) != selected_manifest['parent_manifest_sha256']:
        raise ValueError('parent manifest hash mismatch')
    selected = set(selected_manifest['selected_ids'])
    found, representatives, raw_hashes = {}, {}, {}
    for task in parent['tasks']:
        path = root/(task['id']+'.jsonl.gz')
        with gzip.open(path, 'rt') as stream:
            for line in stream:
                record = json.loads(line)
                cfg = record['config']
                cid = record['config_id']
                expected = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
                if expected != cid:
                    raise ValueError('configuration hash mismatch')
                item = dict(config_id=cid, config=cfg, task=task, parent_raw=str(path.resolve()))
                if cid in selected:
                    found[cid] = item
                mp = cfg['mapping']
                # Extra fair cases cover three physical memories and serial/k=1/2/3.
                if (cfg['requests'] == 120 and task['cores'] == 8
                        and task['track'] == 'neusim_unsliced_hybrid'
                        and task['memory'] in ('M-H256', 'M-L256', 'M-L512')
                        and mp['bw_policy'] == 'fair' and mp['stream_partition'] is None
                        and (mp['mode'] == 'serial' or mp['vlm_cores'] == 6)):
                    representatives[task['memory'], mp['mode'], mp['dit_stages']] = item
        if any(x['parent_raw'] == str(path.resolve()) for x in [*found.values(), *representatives.values()]):
            raw_hashes[str(path.resolve())] = digest(path)
    if set(found) != selected or len(selected) != 10:
        raise ValueError('expected exactly ten matched frozen selections')
    items = {**found, **{r['config_id']: r for r in representatives.values()}}
    for item in items.values():
        item['jit_diagnostic'] = item['config_id'] in selected
    return list(items.values()), dict(parent_manifest_sha256=digest(parent_path),
        selection_manifest_sha256=digest(selected_path), parent_raw_sha256=raw_hashes,
        selected_ids=sorted(selected))


def search_period(evaluate, upper, resolution=.0001, cap=10., max_expansions=18):
    """Return an observed passing bracket; flag observed nonmonotonicity."""
    trials = {}
    def check(t):
        t = float(t)
        if t not in trials:
            trials[t] = evaluate(t)
        return trials[t]['pass_gate']
    lo, hi = 0., min(cap, max(resolution, upper))
    expansions = 0
    while not check(hi):
        lo = hi
        if hi >= cap or expansions >= max_expansions:
            return dict(status='upper_bound_exhausted', Tmin_s=None, trials=trials)
        hi = min(cap, hi*1.5)
        expansions += 1
    while hi-lo > resolution:
        mid = (lo+hi)/2
        if check(mid):
            hi = mid
        else:
            lo = mid
    return dict(status='bracket_found', Tmin_s=hi, lower_failed_s=lo,
                bracket_width_s=hi-lo, trials=trials)


def observed_nonmonotonic(trials):
    seen_pass = False
    for t, gate in sorted(trials.items()):
        if seen_pass and not gate['pass_gate']:
            return True
        seen_pass |= gate['pass_gate']
    return False


def make_sim(item, snapshot):
    cfg, task = item['config'], item['task']
    wl = Pi05Workload()
    provider = NeuSimTiming(snapshot, wl, allow_analytical_siglip=True) if task['track'] == 'neusim_unsliced_hybrid' else None
    dram = DRAMModel(**task['calibration']['params'], version=task['calibration']['version'])
    return HWConfig(**cfg['hardware']), MapConfig(**cfg['mapping']), wl, provider, dram


def run_item(item, output, snapshot, jit_requests, upper_cap):
    out = Path(output)/item['config_id']
    out.mkdir(exist_ok=False)
    hw, mapping, wl, provider, dram = make_sim(item, snapshot)
    k = mapping.dit_stages if mapping.mode == 'pipelined' else 1
    def run(mp, n):
        return Simulator(hw, mp, wl=wl, dram=dram, compute_time_fn=provider).run(n, n//5, diagnostics=True)
    jit = {}
    if item['jit_diagnostic']:
        for name, freeze in (('jit', None), ('frozen20', 20)):
            result = run(replace(mapping, vlm_launch='jit', jit_freeze_after=freeze), jit_requests)
            with gzip.open(out/(name+'.json.gz'), 'wt') as stream:
                json.dump(result, stream, allow_nan=False)
            rows = [r for r in result['requests'] if r['steady_state']]
            rounds = [r for r in result['dit_rounds'] if r.get('steady_state', False)]
            if not rounds:
                ids = {r['request_id'] for r in rows}
                rounds = [r for r in result['dit_rounds'] if any(i in ids for i in r['stage_request_ids'])]
            seq = dict(L=[r['L_s'] for r in rows], S=[r['S_s'] for r in rows if r['S_s'] is not None],
                       VLMduration=[r['vlm_end_s']-r['vlm_start_s'] for r in rows],
                       round_duration=[r['duration_s'] for r in rounds],
                       round_wait=[r['wait_before_s'] for r in rounds],
                       round_active=[sum(i is not None for i in r['stage_request_ids']) for r in rounds])
            jit[name] = {key: series_analysis(values) for key, values in seq.items()}
            jit[name]['predictor'] = result['jit_predictor']
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        for name in jit:
            with gzip.open(out/(name+'.json.gz'), 'rt') as stream:
                rows = json.load(stream)['requests']
            for ax, metric in zip(axes, ('L_s', 'S_s')):
                valid = [r for r in rows if r[metric] is not None]
                ax.plot([r['request_id'] for r in valid], [1000*r[metric] for r in valid], label=name, linewidth=.7)
                ax.set_ylabel(metric[0]+' (ms)')
                ax.legend()
        axes[-1].set_xlabel('Request index')
        fig.suptitle(item['config_id'][:12]+' / '+item['task']['track'])
        fig.tight_layout()
        fig.savefig(out/'LS_timeseries.png', dpi=140)
        plt.close(fig)
    all_trials = {}
    with gzip.open(out/'periodic.jsonl.gz', 'wt') as raw:
        def evaluate(t, n=480):
            result = run(replace(mapping, vlm_launch='periodic', launch_period_s=t, jit_freeze_after=None), n)
            gate = periodic_gate(result, t, k)
            raw.write(json.dumps(dict(T_s=t, requests=n, gate=gate, result=result), allow_nan=False)+'\n')
            all_trials[t, n] = gate
            return gate
        reference_s = float(item.get('initial_period_s', .1))
        search = search_period(evaluate, reference_s, cap=upper_cap)
        curve = []
        if search['Tmin_s'] is not None:
            for factor in (1., 1.1, 1.25, 1.5, 2.):
                t = search['Tmin_s']*factor
                gate = all_trials.get((t, 480))
                if gate is None:
                    gate = evaluate(t)
                confirmation = evaluate(t, 960) if gate['pass_gate'] else None
                curve.append(dict(factor=factor, T_s=t, gate480=gate, gate960=confirmation))
        trials480 = {t: gate for (t, n), gate in all_trials.items() if n == 480}
        nonmonotonic = observed_nonmonotonic(trials480)
        if nonmonotonic:
            search['status'] = 'observed_nonmonotonic_binary_assumption_failed'
    search['trials'] = [dict(T_s=t, **g) for t, g in sorted(trials480.items())]
    summary = dict(config_id=item['config_id'], config=item['config'], track=item['task']['track'],
                   jit_diagnostic=item['jit_diagnostic'], jit=jit, search=search, curve=curve,
                   all_curve_confirmed=bool(curve and all(r['gate960'] and r['gate960']['pass_gate'] for r in curve)),
                   observed_nonmonotonic=nonmonotonic,
                   minimum_scope='finite_horizon_observed_bracket_not_global_proof')
    if jit:
        before = all(jit['jit'][m]['drift_fraction'] < .005 for m in ('L', 'S'))
        after = all(jit['frozen20'][m]['drift_fraction'] < .005 for m in ('L', 'S'))
        summary['feedback_diagnosis'] = ('freeze_removed_observed_drift_supports_feedback_hypothesis_not_causal_proof'
            if not before and after else 'freeze_not_sufficient_or_baseline_already_bounded_check_wait_batch_interaction')
    write_json(out/'summary.json', summary)
    return summary


def collect(out):
    out = Path(out)
    manifest = json.loads((out/'experiment_manifest.json').read_text())
    summaries = [json.loads((out/i['config_id']/'summary.json').read_text()) for i in manifest['items']]
    rows, curves = [], []
    for s in summaries:
        cfg = s['config']
        rows.append(dict(config_id=s['config_id'], memory=cfg['memory'], track=s['track'],
            mode=cfg['mapping']['mode'], k=cfg['mapping']['dit_stages'], policy=cfg['mapping']['bw_policy'],
            Tmin_s=s['search']['Tmin_s'], search_status=s['search']['status'],
            all_curve_confirmed=s['all_curve_confirmed'], nonmonotonic=s['observed_nonmonotonic'],
            feedback_diagnosis=s.get('feedback_diagnosis', 'not_selected_for_jit')))
        for c in s['curve']:
            for n, key in ((480, 'gate480'), (960, 'gate960')):
                if c[key]:
                    curves.append(dict(config_id=s['config_id'], factor=c['factor'], T_s=c['T_s'], requests=n,
                                       **{k: v for k, v in c[key].items() if k != 'adjacent_groups'}))
    write_csv(out/'Tmin.csv', rows)
    write_csv(out/'L_of_T.csv', curves)
    jit_rows = []
    for s in summaries:
        for mode, analyses in s['jit'].items():
            for metric, a in analyses.items():
                if metric == 'predictor':
                    continue
                jit_rows.append(dict(config_id=s['config_id'], mode=mode, metric=metric,
                    classification=a['classification'], strict_period_requests=a['strict_period_requests'],
                    drift_fraction=a['drift_fraction'], **a['batch_means']))
    write_csv(out/'jit_analysis.csv', jit_rows)
    status = dict(configurations=len(summaries), jit_pairs=sum(s['jit_diagnostic'] for s in summaries),
        periodic_all_strict=all(s['all_curve_confirmed'] for s in summaries),
        failed_ids=[s['config_id'] for s in summaries if not s['all_curve_confirmed']],
        nonmonotonic_ids=[s['config_id'] for s in summaries if s['observed_nonmonotonic']],
        gate='P0B_finite_horizon_only_not_DRAM_validation',
        source_manifest_sha256=digest(out/'experiment_manifest.json'),
        artifact_sha256={str(p.relative_to(out)): digest(p) for p in sorted(out.rglob('*'))
                         if p.is_file() and p.name != 'status.json'})
    write_json(out/'status.json', status)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path('results/case_v3_complete'))
    ap.add_argument('--snapshot', type=Path, default=Path('.native/compute'))
    ap.add_argument('--out', type=Path, default=Path('results/v4/p0b'))
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--jit-requests', type=int, default=1920)
    ap.add_argument('--upper-cap', type=float, default=10.)
    ap.add_argument('--collect-only', action='store_true')
    args = ap.parse_args()
    if args.collect_only:
        print(json.dumps(collect(args.out), default=str))
        return
    items, provenance = load_selection(args.root)
    args.out.mkdir(parents=True, exist_ok=False)
    source_root = Path(__file__).resolve().parent
    sources = [Path(__file__).resolve(), source_root/'case_v3_main.py', source_root/'compute_diagnostics.py',
               *sorted((source_root/'vlasim').glob('*.py'))]
    hashes = {}
    for path in sources:
        relative = path.relative_to(source_root)
        target = args.out/'executed_sources'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(relative)] = digest(path)
    write_json(args.out/'experiment_manifest.json', dict(**provenance, items=items,
        source_hashes=hashes, snapshot_manifest_sha256=digest(args.snapshot/'source_manifest.json'),
        jit_requests=args.jit_requests, jit_warmup=args.jit_requests//5,
        periodic_requests=[480, 960], periodic_warmup=[96, 192],
        search_resolution_s=.0001, upper_cap_s=args.upper_cap,
        upper_expansion_limit=18, factors=[1, 1.1, 1.25, 1.5, 2],
        strict_tolerance_s=1e-9, independent_experiment_CI=False,
        extra_selection='8core real-NeuSim fair serial and 6:2 pipeline k1/2/3 across three unpartitioned memories',
        versions=dict(numpy=np.__version__)))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_item, i, str(args.out.resolve()), str(args.snapshot.resolve()),
                               args.jit_requests, args.upper_cap) for i in items]
        for f in as_completed(futures):
            s = f.result()
            print('finished', s['config_id'][:12], s['search']['status'], s['all_curve_confirmed'], flush=True)
    status = collect(args.out)
    print(json.dumps({k: v for k, v in status.items() if k != 'artifact_sha256'}), flush=True)


if __name__ == '__main__':
    main()
