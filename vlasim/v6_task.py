"""Prepare unexecuted closed-loop requests and validate author-supplied episode logs."""
import argparse
import csv
from pathlib import Path

from v6_common import ROOT,load,write_json,write_csv,digest
from v51_package import read_csv

METADATA=('checkpoint_sha256','environment_version','latency_injection_implementation','chunk_adoption_rule')


def summarize(records):
    rows=[]
    for r in records:
        if any(not r.get(k) for k in ('point_id','speed_band',*METADATA)):
            raise ValueError('Missing speed/checkpoint/environment/injection/chunk metadata')
        attempted,success,invalid=(int(r[k]) for k in ('trials','successes','invalid_trials'))
        if attempted<=0 or not 0<=invalid<=attempted or not 0<=success<=attempted-invalid:
            raise ValueError('Counts must satisfy 0 <= successes <= valid_trials <= trials')
        valid=attempted-invalid
        rows.append(dict(r,valid_trials=valid,success_rate_invalid_as_failure=success/attempted,
            success_rate_invalid_excluded=success/valid if valid else None))
    return rows


def prepare():
    out=ROOT/'task';out.mkdir(exist_ok=True)
    points=read_csv(ROOT/'paper/selected_conditional_points.csv');allpoints=read_csv(ROOT/'paper/candidate_points.csv')
    chosen={}
    for r in points:
        key=(round(float(r['L_s']),9),round(float(r['S_s']),9))
        if key not in chosen:
            chosen[key]=dict(point_id=r['point_id'],L_ms=float(r['L_s'])*1000,S_ms=float(r['S_s'])*1000,
                hardware_id=r['hardware_id'],mode=r['mode'],k=r['dit_stages'],batching=r['dit_batching'],
                role='conditional_within_memory_selection_NOT_global_cost_selection',status='not_measured')
    added=[];pool=[r for r in allpoints if float(r['L_s'])<.1]
    for target in (25,40,55,70,85,95):
        options=[r for r in pool if (round(float(r['L_s']),9),round(float(r['S_s']),9)) not in chosen]
        if not options:raise RuntimeError('Fewer than six additional distinct sub100ms candidate points')
        r=min(options,key=lambda r:(abs(float(r['L_s'])*1000-target),float(r['S_s']),r['point_id']))
        key=(round(float(r['L_s']),9),round(float(r['S_s']),9))
        chosen[key]=dict(point_id=r['point_id'],L_ms=float(r['L_s'])*1000,S_ms=float(r['S_s'])*1000,
            hardware_id=r['hardware_id'],mode=r['mode'],k=r['dit_stages'],batching=r['dit_batching'],
            role='additional_sub100ms_simulated_point_NOT_task_measurement',status='not_measured')
        added.append(r['point_id'])
    write_csv(out/'points.csv',list(chosen.values()))
    rows=[dict(point_id=r['point_id'],L_ms=r['L_ms'],S_ms=r['S_ms'],speed_band=None,
        trials=None,successes=None,invalid_trials=None,**{k:None for k in METADATA}) for r in chosen.values()]
    write_csv(out/'results_template.csv',rows)
    write_json(out/'protocol.json',dict(status='awaiting_author_inputs_not_executed',task_episodes_run=0,
        points=len(chosen),additional_sub100ms=added,speed_bands=None,trials_per_point_per_speed=None,
        checkpoint_sha256=None,environment_version=None,latency_injection_implementation=None,chunk_adoption_rule=None,
        success_definition=None,invalid_episode_definition=None,random_seed_policy=None,
        important='Global cost-optimal pairs cannot be finalized until missing cost coefficients arrive. '
            'Current list deliberately covers conditional per-memory pairs, not claimed global-optimal hardware.'))
    text='''# V6 Closed-Loop Measurement Request

Status: PREPARATION ONLY. No task episodes were executed. All latency/interval values are simulator proposals, not robot/task measurements.

## Inputs Required Before Execution

Fill every null in `protocol.json`: checkpoint SHA256/version, environment build/version, actual speed-band definitions, trial budget per point/speed, success criterion, invalid-episode criterion, random-seed policy, latency injection implementation and chunk adoption rule. Do not silently choose a trial budget or speed band. Record hardware/controller limits and timestamps used for both latency and interval.

## Point List

`points.csv` deduplicates (L,S) from the nominal **within-memory conditional area selections** and adds exactly six distinct simulated points with L<100ms. The global minimum-cost selections required by V6 are blocked by missing PHY/DRAM cost coefficients. This is a superset-style conditional measurement proposal, NOT the finalized global-cost list. After coefficients are supplied, rerun the paper selection and regenerate this request before committing lab resources.

## Execution Contract

For each point and each author-defined speed band, run the agreed number of independent closed-loop trials. Inject observation-to-completed-action latency L and action/chunk completion interval S separately using monotonic timestamps; log requested and realized L/S and their distribution. Define whether late observations are queued/dropped and whether a new chunk replaces or appends pending actions. The experiment owner must confirm the environment can realize each requested pair; infeasible injection points are recorded, not silently rounded.

Save one row per point/speed/checkpoint/environment/protocol version in `results_template.csv`, duplicating rows for every speed band. `trials` counts ALL attempts, `invalid_trials` counts attempts invalid under the declared rule, and `successes` counts successes only among valid attempts. Preserve per-episode IDs, seeds, outcomes, invalid reasons and actual timing logs as immutable referenced artifacts.

## Two Mandatory Summaries

Let N=trials, I=invalid_trials, K=valid successes. Report both K/N (invalid counted as failure) and K/(N-I) (invalid excluded). If all trials are invalid, the excluded rate is null, not zero. Never merge speed bands or mix checkpoints/injection protocols.

Validate and summarize only genuine supplied results:

```sh
PYTHONPATH=vlasim .venv/bin/python vlasim/v6_task.py validate --input AUTHOR_RESULTS.csv --output AUTHOR_SUMMARY.csv
```

The blank template intentionally fails validation until external inputs and measured counts are supplied. This validator never launches a robot/environment and does not generate successes.
'''
    (out/'measurement_request.md').write_text(text)
    write_json(out/'status.json',dict(points=len(chosen),additional_sub100ms=6,task_episodes_run=0,
        global_selection_finalized=False,source_sha256=digest(__file__),
        hashes={name:digest(out/name) for name in ('points.csv','protocol.json','results_template.csv','measurement_request.md')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','validate'));p.add_argument('--input');p.add_argument('--output');a=p.parse_args()
    if a.action=='prepare':prepare()
    else:write_csv(Path(a.output),summarize(read_csv(Path(a.input))))
