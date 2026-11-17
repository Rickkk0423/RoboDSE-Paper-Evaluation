"""Checkpoint actual completed shards without promoting an unfinished DSE gate."""
from collections import defaultdict

from v51_workflow import ROOT,load
from v5_protocol import write_json


def checkpoint():
    paths=list((ROOT/'dse/shards').glob('*/status.json'))
    groups=defaultdict(list)
    for path in paths:
        row=load(path);groups[row['memory'].split('_')[0]].append(row)
    phases={name:dict(completed_shards=len(rows),expected_shards=32 if name=='LPDDR5' else 24,
        mapping_rows=sum(r['rows'] for r in rows),curve_rows=sum(r['curve_rows'] for r in rows),
        reference_rechecks=sum(r['reference_rechecks'] for r in rows)) for name,rows in groups.items()}
    write_json(ROOT/'dse/phase_summary.json',phases)
    gates=load(ROOT/'gates.json')
    if gates['stage4']['status'] in ('pending','running','completed_awaiting_packaging'):
        execution=load(ROOT/'execution/dse_local.json')
        gates['stage4']=dict(status='completed_awaiting_packaging' if execution['status']=='completed' else execution['status'],
            completed_shards=len(paths),expected_shards=80,phases=phases)
        write_json(ROOT/'gates.json',gates)
    print(phases,flush=True)


if __name__=='__main__':
    checkpoint()
