"""Audit the completed V5 protocol stage without promoting a failed hard gate."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml

from v5_protocol import digest, write_json


def compare_values(left, right, tolerance=1e-6, path=''):
    """Absolute tolerance for native numeric fields, exact structure and identities."""
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            return [dict(path=path, reason='different keys')]
        return [d for key in left for d in compare_values(left[key], right[key], tolerance, path+'.'+key)]
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [dict(path=path, reason='different lengths')]
        return [d for i, (a, b) in enumerate(zip(left, right))
                for d in compare_values(a, b, tolerance, path+f'[{i}]')]
    if (isinstance(left, (int, float)) and not isinstance(left, bool)
            and isinstance(right, (int, float)) and not isinstance(right, bool)):
        if abs(left-right) <= tolerance:
            return []
    elif type(left) is type(right) and left == right:
        return []
    return [dict(path=path, left=left, right=right)]


def accounting(native, raw, expected_bytes):
    controllers = raw['controller']
    reads, writes = raw['total_num_read_requests'], raw['total_num_write_requests']
    served_reads = sum(c.get('num_read_reqs_served', 0) + c.get('num_read_reqs_forwarded', 0)
                       for c in controllers)
    served_writes = sum(c.get('num_write_reqs_served', 0) + c.get('num_write_reqs_coalesced', 0)
                        for c in controllers)
    return (native['accepted'] == native['completed'] == reads+writes
            == sum(native['stream_transactions']) and reads == served_reads and writes == served_writes
            and native['logical_bytes'] == native['accepted']*32 == expected_bytes)


def pytest_summary(path):
    suites = ET.parse(path).getroot().iter('testsuite')
    totals = dict.fromkeys(('tests', 'failures', 'errors', 'skipped'), 0)
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, 0))
    if not totals['tests'] or totals['failures'] or totals['errors']:
        raise RuntimeError('test gate failed or empty')
    return totals


def audit(root):
    prepared = root/'selfcheck_input_v2'
    manifest = json.loads((prepared/'manifest.json').read_text())
    expected = {w['id']: w for w in manifest['windows']}
    hosts, findings = {}, []
    for host in ('local', 'remote'):
        directory = root/f'selfcheck_{host}_v2'
        rows = {}
        for shard in sorted(directory.glob('shard_*')):
            frozen = json.loads((shard/'manifest.json').read_text())
            if frozen['input_manifest_sha256'] != digest(prepared/'manifest.json'):
                raise RuntimeError('input manifest hash mismatch')
            for source, wanted in frozen['source_hashes'].items():
                if digest(shard/source) != wanted:
                    raise RuntimeError('archived executed source hash mismatch')
            completed = json.loads((shard/'completed.json').read_text())['windows']
            if set(completed) != {w['id'] for w in frozen['windows']}:
                raise RuntimeError('shard completion list mismatch')
            for window in frozen['windows']:
                label = window['id']
                if label in rows or window != expected[label]:
                    raise RuntimeError('duplicate or changed frozen window')
                if digest(prepared/window['trace']) != window['trace_sha256']:
                    raise RuntimeError('trace hash mismatch')
                row = json.loads((shard/(label+'.json')).read_text())
                if row['window'] != window:
                    raise RuntimeError('result does not match frozen window')
                raw = yaml.safe_load((shard/(label+'_stats.yaml')).read_text())['memory_system']
                if (not accounting(row['native'], raw, sum(window['bytes_by_stream']))
                        or [n*32 for n in row['native']['stream_transactions']] != window['bytes_by_stream']):
                    findings.append(dict(host=host, window=label, gate='native_accounting'))
                reference = manifest['case']['calibration']['params']['eta_seq'] * row['geometry']['peak_GBps']
                end = max(x for x in row['native']['last_completion_ns'] if x is not None)
                ratio = row['native']['logical_bytes']/end/reference
                if abs(ratio-row['total_over_seq_reference']) > 1e-12:
                    raise RuntimeError('reported throughput ratio cannot be reproduced')
                row['ratio_recomputed'] = ratio
                rows[label] = row
        if set(rows) != set(expected):
            raise RuntimeError(f'incomplete {host} selfcheck')
        hosts[host] = rows
    cross = []
    exact = True
    for label in expected:
        a, b = hosts['local'][label], hosts['remote'][label]
        cross += compare_values(a['native'], b['native'], path=label)
        cross += compare_values(a['geometry'], b['geometry'], path=label+'.geometry')
        cross += compare_values(a['large_hbm_identity'], b['large_hbm_identity'], path=label+'.hbm')
        cross += compare_values(a['ratio_recomputed'], b['ratio_recomputed'], path=label+'.ratio')
        exact &= a['native'] == b['native'] and a['ratio_recomputed'] == b['ratio_recomputed']
    local_probe = json.loads((root/'driver_equivalence_local_v2/status.json').read_text())
    remote_probe = json.loads((root/'driver_equivalence_remote_v2/status.json').read_text())
    if not local_probe['exact'] or not remote_probe['exact']:
        raise RuntimeError('reference driver equivalence failed')
    probe_pairs = zip(local_probe['comparisons'], remote_probe['comparisons'])
    if len(local_probe['comparisons']) != 6 or len(remote_probe['comparisons']) != 6:
        raise RuntimeError('incomplete native equivalence probes')
    for a, b in probe_pairs:
        if a['id'] != b['id']:
            raise RuntimeError('different native probe configuration')
        cross += compare_values(a['native'], b['native'], path=a['id'])
        exact &= a['native'] == b['native']
    saturated = [r for r in hosts['remote'].values() if r['window']['launch'] == 'saturated']
    passed = all(r['ratio_recomputed'] >= .90 for r in saturated)
    failures = []
    if findings:
        failures.append('native_accounting_mismatch')
    if cross:
        failures.append('cross_host_difference_exceeds_1e-6')
    if not passed:
        failures.append('block_sampling_selfcheck_below_0.90')
    hbm = next(iter(hosts['remote'].values()))['large_hbm_identity']
    if hbm['geometry']['capacity_bytes'] < 8*1024**3:
        raise RuntimeError('exported HBM below requested capacity')
    gates = dict(spec='NEXT_STEPS_V5.md', spec_document_date='2026-11-16',
                 execution_local_date='2026-11-15', timezone='America/Los_Angeles',
                 status='hard_stopped' if failures else 'protocol_pass_ready_for_step2',
                 hard_stop_reasons=failures, dram_model_mode='not_selected_no_v5_dse',
                 step1=dict(traffic_reconciliation=dict(status='pass',
                     scope='generator component/op guard and all 8 completed sampled-byte audits'),
                     native_accounting=dict(status='fail' if findings else 'pass', findings=findings),
                     reference_driver_equivalence=dict(status='pass', local_probes=6, remote_probes=6),
                     cross_host=dict(status='fail' if cross else 'pass', tolerance=1e-6,
                         complete_W5_pairs=4, probe_pairs=6, all_exact=bool(exact), differences=cross),
                     block_sampling=dict(status='pass' if passed else 'fail', threshold=.90,
                         results=[dict(id=k, host=host, ratio=r['ratio_recomputed'],
                             launch=r['window']['launch'], native_bytes=r['native']['logical_bytes'],
                             transactions=r['native']['completed'])
                             for host, rows in hosts.items() for k, r in rows.items()],
                         physical_row_bytes=2048, labels_coincide=True),
                     hbm=dict(status='exported_not_native_validated', config=hbm['config'],
                         capacity_bytes=hbm['geometry']['capacity_bytes'],
                         yaml_sha256=hbm['geometry']['yaml_sha256']),
                     tests=pytest_summary(root/'validation/local_pytest.xml')),
                 step2=dict(status='not_executed_hard_stop', fit_windows=0, heldout_windows=0),
                 step3=dict(status='not_executed_hard_stop', calibrated_memory_tiers=0),
                 step4=dict(status='not_executed_hard_stop', executed_hardware_points=0,
                            simulated_mapping_points=0, pruned_mapping_points=0),
                 step5=dict(status='not_executed_no_v5_frontier', measured_task_episodes=0))
    write_json(root/'gates.json', gates)
    return gates


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('results/v5'))
    args = parser.parse_args()
    result = audit(args.root)
    print(result['status'], result['hard_stop_reasons'])
