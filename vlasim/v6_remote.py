"""Resume-safe V6 Slurm stages; preserve failed attempts and audit job accounting."""
import argparse
from pathlib import Path
import shutil
import time

from v6_common import ROOT,load,write_json,digest
from v51_remote import REMOTE,command


def batch(stage):
    source=ROOT/(stage+'_input');manifest=load(source/'manifest.json')
    execution=ROOT/'execution';execution.mkdir(parents=True,exist_ok=True)
    history=execution/(stage+'_jobs.json');attempts=load(history) if history.exists() else []
    command(['rsync','-a','vlasim/ramulator_bridge/v6_native.py',f'einst:{REMOTE}/vlasim/ramulator_bridge/'])
    command(['rsync','-a','scripts/einst_v6.sh',f'einst:{REMOTE}/scripts/'])
    command(['rsync','-a',str(source)+'/',f'einst:{REMOTE}/results/v6_{stage}_input/'])
    target=ROOT/(stage+'_native')
    for attempt in range(3):
        pending=[i for i in range(len(manifest['items'])) if not (target/f'shard_{i}/status.json').exists()]
        if not pending:
            break
        index=len(attempts);remote_output=f'results/v6_{stage}_native_attempt{index}'
        concurrency=4 if not attempts else 1
        shell=f'sbatch --parsable --chdir={REMOTE} --array={",".join(map(str,pending))}%{concurrency} '+\
            f'--time=00:{10+10*attempt:02d}:00 --export=ALL,V6_INPUT=results/v6_{stage}_input,V6_OUTPUT={remote_output} '+\
            f'{REMOTE}/scripts/einst_v6.sh'
        job=command(['ssh','einst',shell]).strip().split(';')[0]
        if not job.isdigit():
            raise RuntimeError('Invalid Slurm response '+job)
        record=dict(job_id=int(job),indices=pending,concurrency=concurrency,command=shell,
            source_manifest_sha256=digest(source/'manifest.json'),native_source_sha256=digest('vlasim/ramulator_bridge/v6_native.py'),
            remote_output=remote_output)
        attempts.append(record);write_json(history,attempts)
        print('Submitted',stage,job,len(pending),'shards',flush=True)
        while command(['ssh','einst',f'squeue -h -j {job}']).strip():
            time.sleep(20)
        record['accounting']=command(['ssh','einst',f'sacct -j {job} --format=JobID,State,ExitCode,Elapsed,MaxRSS --noheader'])
        dest=ROOT/(stage+f'_attempt{index}')
        command(['rsync','-a',f'einst:{REMOTE}/{remote_output}/',str(dest)+'/'])
        logs=execution/(stage+'_'+job);logs.mkdir(exist_ok=True)
        failures=[]
        for i in pending:
            result=dest/f'shard_{i}'
            log=command(['ssh','einst',f'cat {REMOTE}/slurm-v6-{job}_{i}.log'])
            (logs/f'shard_{i}.log').write_text(log)
            if (result/'failure.json').exists():
                failure=load(result/'failure.json');failures.append(dict(index=i,**failure))
                if 'HARD_STOP' in failure['message'] or 'accounting' in failure['message'] or 'offered/completed' in failure['message']:
                    record['failures']=failures;write_json(history,attempts)
                    raise RuntimeError('HARD_STOP_native '+str(failure))
            if (result/'status.json').exists():
                target.mkdir(exist_ok=True)
                shutil.copytree(result,target/f'shard_{i}')
        record['failures']=failures;write_json(history,attempts)
        if failures:
            raise RuntimeError('Implementation/backend failure preserved; inspect '+str(failures))
        incomplete=[i for i in pending if not (target/f'shard_{i}/status.json').exists()]
        if incomplete and not any(s in record['accounting'] for s in ('OUT_OF_MEMORY','TIMEOUT','NODE_FAIL','PREEMPTED')):
            raise RuntimeError('Unexpected incomplete shards '+str(incomplete))
    if any(not (target/f'shard_{i}/status.json').exists() for i in range(len(manifest['items']))):
        raise RuntimeError('Resource retries exhausted')
    print('Completed',stage,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage');a=p.parse_args();batch(a.stage)
