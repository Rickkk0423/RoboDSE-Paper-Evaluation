"""Re-open final delivery hashes and reject missing, altered or failed-stage evidence."""
from pathlib import Path
import csv

from v51_workflow import ROOT,load
from v5_protocol import digest,write_json


def verify():
    manifest=load(ROOT/'delivery_manifest.json');failures=[]
    for name,sha in manifest['artifacts_sha256'].items():
        path=ROOT/name
        if not path.is_file() or digest(path)!=sha:
            failures.append(str(path))
    for name,sha in manifest['sources_sha256'].items():
        if not Path(name).is_file() or digest(name)!=sha:
            failures.append(name)
    if failures:
        raise RuntimeError('Delivery hash verification failed '+str(failures))
    summary=load(ROOT/'dse_summary.json')
    if summary['hardware_points']!=640 or not load(ROOT/'native_archive_audit.json')['passed'] or not load(ROOT/'dse_archive_audit.json')['passed']:
        raise RuntimeError('Incomplete DSE or failed native archive audit')
    if load(ROOT/'dse_archive_audit.json')['evaluations']!=summary['unique_semantic_evaluations']+summary['supplemental_semantic_evaluations']:
        raise RuntimeError('DSE archive audit coverage mismatch')
    if load(ROOT/'task_preparation/status.json')['measured_episodes']!=0:
        raise RuntimeError('Unexpected task episode claim')
    with (ROOT/'attainable.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['canonical960_pass']!='True':
                raise RuntimeError('Unconfirmed attainable frontier')
    print('Final delivery verified:',len(manifest['artifacts_sha256']),'artifacts,',
          len(manifest['sources_sha256']),'sources/report hashes, 640 hardware points',flush=True)


if __name__=='__main__':
    verify()
