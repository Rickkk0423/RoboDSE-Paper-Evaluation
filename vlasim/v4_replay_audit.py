"""Audit frozen native replay evidence without fitting or changing acceptance."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import yaml
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acceptance(errors, *, complete, coverage_complete, integrity_ok):
    mean = sum(errors) / len(errors) if errors else None
    numerical = bool(errors) and max(errors) <= 10 and mean <= 5
    return dict(mean_absolute_error_pct=mean,
                maximum_absolute_error_pct=max(errors) if errors else None,
                numerical_thresholds_pass=numerical,
                passed=bool(numerical and complete and coverage_complete and integrity_ok))


def audit(inputs, native, out):
    manifest = json.loads((inputs / 'manifest.json').read_text())
    expected = {w['id']: w for w in manifest['windows']}
    cases = {c['name']: c for c in manifest['cases']}
    issues, rows, seen, backend_ids = [], [], set(), []
    shards = sorted(native.glob('shard_*'))
    complete_shards = 0
    for shard in shards:
        sm = json.loads((shard / 'manifest.json').read_text())
        if sm['shards'] != 8 or shard.name != f"shard_{sm['shard']}" or not 0 <= sm['shard'] < 8:
            issues.append(f'{shard.name}: invalid shard identity')
        if sm['input_manifest_sha256'] != sha(inputs / 'manifest.json'):
            issues.append(f'{shard.name}: input manifest hash differs')
        for name, digest in sm['source_hashes'].items():
            if sha(shard / 'executed_sources' / name) != digest:
                issues.append(f'{shard.name}: source hash differs: {name}')
        done = shard / 'completed.json'
        if done.exists():
            completion = json.loads(done.read_text())
            if completion['manifest_sha256'] != sha(shard / 'manifest.json'):
                issues.append(f'{shard.name}: completion manifest differs')
            if completion['cases'] != len(sm['cases']):
                issues.append(f'{shard.name}: completion case count differs')
            complete_shards += 1
        for window in sm['cases']:
            wid = window['id']
            path = shard / (wid + '.json')
            if not path.exists():
                continue
            if wid in seen or window != expected.get(wid):
                issues.append(f'{wid}: duplicate or non-frozen window')
            seen.add(wid)
            result = json.loads(path.read_text())
            backend_ids.append(result['backend_identity'])
            metadata = cases[window['case']]['calibration']['backend_metadata']
            pinned = dict(source_manifest_sha256=metadata['source_manifest_sha256'],
                          bridge_sha256=metadata['library_sha256'],
                          memory_sha256=metadata['memory_library_sha256'])
            if result['backend_identity'] != pinned:
                issues.append(f'{wid}: backend differs from frozen calibration')
            if result['window'] != window:
                issues.append(f'{wid}: row window differs')
            if sha(inputs / window['trace']) != window['trace_sha256']:
                issues.append(f'{wid}: trace hash differs')
            if sha(shard / (wid + '.yaml')) != result['yaml_sha256']:
                issues.append(f'{wid}: YAML hash differs')
            stats = yaml.safe_load((shard / (wid + '_stats.yaml')).read_text())['memory_system']
            controllers = stats['controller']
            counters = {key: sum(c.get(key, 0) for c in controllers) for key in (
                'num_read_reqs_served', 'num_write_reqs_served',
                'num_read_reqs_forwarded', 'num_write_reqs_coalesced')}
            n = result['native']
            reads, writes = stats['total_num_read_requests'], stats['total_num_write_requests']
            with np.load(inputs / window['trace']) as trace:
                expected_writes = int(np.count_nonzero(trace['write'])) * 2
                expected_reads = len(trace['write']) * 2 - expected_writes
            valid_counts = (reads + writes == n['accepted'] == n['completed']
                            == sum(n['stream_transactions'])
                            and reads == expected_reads and writes == expected_writes
                            and [count * 32 for count in n['stream_transactions']] == window['bytes_by_stream']
                            and n['logical_bytes'] == sum(window['bytes_by_stream']))
            # Forwarded/coalesced requests can complete without a separate DRAM command.
            valid_counts &= (counters['num_read_reqs_served'] + counters['num_read_reqs_forwarded'] == reads)
            valid_counts &= (counters['num_write_reqs_served'] + counters['num_write_reqs_coalesced'] == writes)
            if not valid_counts:
                issues.append(f'{wid}: native accepted/completed/served accounting differs')
            expected_streams = {'vlm' if c == 0 else 'dit' for c, count in enumerate(n['stream_transactions']) if count}
            actual_streams = [m['stream'] for m in result['metrics']]
            if len(actual_streams) != len(set(actual_streams)) or set(actual_streams) != expected_streams:
                issues.append(f'{wid}: missing/duplicate per-stream metric')
            for metric in result['metrics']:
                signed = (metric['actual_duration_ns'] / metric['predicted_duration_ns'] - 1) * 100
                if (abs(signed - metric['signed_error_pct']) > 1e-8
                        or abs(abs(signed) - metric['absolute_error_pct']) > 1e-8):
                    issues.append(f'{wid}: metric calculation differs')
                rows.append(dict(id=wid, case=window['case'], memory=window['memory'],
                    window=window['window'], launch=window['launch'], bg=window['bg'],
                    **metric, passes_10pct=abs(signed) <= 10,
                    total_over_seq_reference=result['total_over_seq_reference'],
                    native_reads=reads, native_writes=writes, accounting_ok=bool(valid_counts),
                    **counters))
    if backend_ids and any(b != backend_ids[0] for b in backend_ids):
        issues.append('native backend identity differs between windows')
    missing = sorted(set(expected) - seen)
    gaps = [u for u in manifest['unavailable'] if u['reason'] != 'not applicable to this mode/k']
    complete = not missing and complete_shards == 8 and len(shards) == 8
    gate = acceptance([r['absolute_error_pct'] for r in rows], complete=complete,
                      coverage_complete=not gaps, integrity_ok=not issues)
    groups = {}
    for launch in ('open', 'saturated'):
        group = [r for r in rows if r['launch'] == launch]
        groups[launch] = dict(stream_measurements=len(group),
            mean_absolute_error_pct=sum(r['absolute_error_pct'] for r in group)/len(group) if group else None,
            maximum_absolute_error_pct=max((r['absolute_error_pct'] for r in group), default=None),
            failures_over_10pct=sum(not r['passes_10pct'] for r in group))
    window_means = [sum(r['absolute_error_pct'] for r in rows if r['id'] == wid)
                    / sum(r['id'] == wid for r in rows) for wid in seen
                    if any(r['id'] == wid for r in rows)]
    by_window = {}
    for kind in ('W1', 'W2', 'W3', 'W4', 'W5'):
        group = [r for r in rows if r['window'] == kind]
        by_window[kind] = dict(stream_measurements=len(group),
            mean_absolute_error_pct=sum(r['absolute_error_pct'] for r in group)/len(group) if group else None,
            maximum_absolute_error_pct=max((r['absolute_error_pct'] for r in group), default=None),
            failures_over_10pct=sum(not r['passes_10pct'] for r in group))
    status = dict(status='passed' if gate['passed'] else 'not_passed',
        input_manifest_sha256=sha(inputs / 'manifest.json'), expected_windows=len(expected),
        completed_windows=len(seen), stream_measurements=len(rows),
        complete_shards=complete_shards, missing_windows=missing, integrity_issues=issues,
        coverage_gaps=gaps, unavailable=manifest['unavailable'],
        summary_by_launch=groups,
        summary_by_window=by_window,
        mean_of_window_mean_absolute_errors_pct=sum(window_means)/len(window_means) if window_means else None,
        bg_total_over_seq_reference={r['id']: r['total_over_seq_reference'] for r in rows if r['bg']},
        failing_streams=[r for r in rows if not r['passes_10pct']],
        backend_identity=backend_ids[0] if backend_ids else None, **gate,
        scope='Model-derived estimated shapes/layout, not independent execution capture. '
              'W5 is time-compressed 1/10 line sampling; locality changes. '
              'Saturated native demand-proportional merged offering is compared with '
              'fluid infinite-demand max-min fair; native FRFCFS does not guarantee '
              'that per-stream share, so deviations include frontend/arbitration assumptions. '
              'Priority/balance not validated. No fitting on these replay windows.')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    if rows:
        with (out / 'stream_metrics.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--native', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    status = audit(args.input, args.native, args.out)
    print(json.dumps({k: status[k] for k in ('status', 'completed_windows',
        'stream_measurements', 'mean_absolute_error_pct', 'maximum_absolute_error_pct',
        'integrity_issues')}, indent=2))


if __name__ == '__main__':
    main()
