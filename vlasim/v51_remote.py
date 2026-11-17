"""Record isolated Slurm replay execution and retry resource failures only."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from v5_protocol import digest,write_json

REMOTE='/tmp/vlasim_phase4_20261115.Os3Bob'
ROOT=Path('results/v5_1')


def command(args):
    for attempt in range(4):
        result=subprocess.run(args,text=True,capture_output=True)
        if not result.returncode:
            return result.stdout
        retryable=any(term in result.stderr for term in ('Connection reset','Connection closed',
            'Connection timed out','Broken pipe','kex_exchange_identification'))
        if not retryable or 'sbatch' in args[-1] or attempt==3:
            raise RuntimeError(f'{args}: {result.stderr}')
        time.sleep(3*(attempt+1))


def batch(stage):
    source=ROOT/(stage+'_input');manifest=json.loads((source/'manifest.json').read_text())
    execution=ROOT/'execution';execution.mkdir(exist_ok=True)
    target=ROOT/(stage+'_native')
    if target.exists():
        raise FileExistsError('Preserve previous native result root; do not overwrite '+str(target))
    remote_input=f'results/v51_{stage}_input'
    command(['rsync','-a',str(source)+'/',f'einst:{REMOTE}/{remote_input}/'])
    pending=list(range(len(manifest['items'])));attempts=[]
    for attempt in range(3):
        if not pending:
            break
        remote_output=f'results/v51_{stage}_native'+(f'_retry{attempt}' if attempt else '')
        concurrency=1 if attempt else 4
        minutes=10*(attempt+1)
        shell=f'sbatch --parsable --chdir={REMOTE} --array={",".join(map(str,pending))}%{concurrency} '+\
            f'--time=00:{minutes:02d}:00 --export=ALL,V51_MODE=batch,V51_INPUT={remote_input},V51_OUTPUT={remote_output} '+\
            f'{REMOTE}/scripts/einst_v51.sh'
        job=command(['ssh','einst',shell]).strip().split(';')[0]
        if not job.isdigit():
            raise RuntimeError('Invalid Slurm job response '+job)
        record=dict(stage=stage,attempt=attempt,job_id=int(job),indices=pending.copy(),
            concurrency=concurrency,mem_GiB=4,time_limit_minutes=minutes,command=shell,
            source_manifest_sha256=digest(source/'manifest.json'),remote_output=remote_output)
        attempts.append(record);write_json(execution/(stage+'_jobs.json'),attempts)
        print('Submitted',stage,job,'indices',pending,'concurrency',concurrency,flush=True)
        while command(['ssh','einst',f'squeue -h -j {job}']).strip():
            time.sleep(20)
        accounting=command(['ssh','einst',f'sacct -j {job} --format=JobID,State,ExitCode,Elapsed,MaxRSS --noheader'])
        record['accounting']=accounting
        logs=execution/f'{stage}_{job}';logs.mkdir(exist_ok=True)
        for index in pending:
            log=command(['ssh','einst',f'cat {REMOTE}/slurm-v51-{job}_{index}.log'])
            (logs/f'shard_{index}.log').write_text(log)
        destination=ROOT/(stage+'_native'+(f'_attempt{attempt}' if attempt else ''))
        command(['rsync','-a',f'einst:{REMOTE}/{remote_output}/',str(destination)+'/'])
        failed=[]
        for index in pending:
            shard=destination/f'shard_{index}'
            if (shard/'failure.json').exists():
                failure=json.loads((shard/'failure.json').read_text())
                record['failure']=failure;write_json(execution/(stage+'_jobs.json'),attempts)
                raise RuntimeError('Native failure (not resource retry): '+str(failure))
            if not (shard/'status.json').exists():
                failed.append(index)
                continue
            if attempt:
                original=target/f'shard_{index}'
                if original.exists():
                    preserved=ROOT/'failed_attempts'/stage/f'attempt0_shard_{index}'
                    preserved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(original),str(preserved))
                shutil.copytree(shard,original)
        if failed and not any(s in accounting for s in ('OUT_OF_MEMORY','TIMEOUT','NODE_FAIL','PREEMPTED')):
            record['unexpected_incomplete']=failed;write_json(execution/(stage+'_jobs.json'),attempts)
            raise RuntimeError('Unexpected incomplete native shard, inspect archived job logs')
        record['resource_retry_indices']=failed
        write_json(execution/(stage+'_jobs.json'),attempts)
        pending=failed
    if pending:
        raise RuntimeError('Resource retries exhausted '+str(pending))
    print('Completed native stage',stage,flush=True)


def archive_history():
    execution=ROOT/'execution';execution.mkdir(exist_ok=True)
    history=[(2047384,'native_equivalence'),(2047430,'selfcheck_9_completed_HBM_OOM'),
        (2047677,'HBM_serial_retry_4minute_timeout'),(2047718,'HBM_serial_retry_success'),
        (2047711,'kernel_missing_module_failure'),(2047984,'kernel_validation_success'),
        (2047992,'development_success')]
    rows=[]
    for job,reason in history:
        accounting=command(['ssh','einst',f'sacct -j {job} --format=JobID,State,ExitCode,Elapsed,MaxRSS --noheader'])
        rows.append(dict(job_id=job,stage=reason,accounting=accounting))
        command(['rsync','-a','--include=*'+str(job)+'*','--exclude=*',f'einst:{REMOTE}/',str(execution)+'/'])
    write_json(execution/'historical_jobs.json',rows)
    command(['rsync','-a',f'einst:{REMOTE}/results/v51_selfcheck_retry1/',str(ROOT/'failed_attempts/selfcheck_timeout')+'/'])


def collect_existing(stage):
    execution=ROOT/'execution';path=execution/(stage+'_jobs.json')
    attempts=json.loads(path.read_text());record=attempts[-1];job=record['job_id']
    if command(['ssh','einst',f'squeue -h -j {job}']).strip():
        raise RuntimeError('Job still running; do not collect incomplete stage')
    destination=ROOT/(stage+'_native')
    command(['rsync','-a',f'einst:{REMOTE}/{record["remote_output"]}/',str(destination)+'/'])
    for index in record['indices']:
        shard=destination/f'shard_{index}'
        if (shard/'failure.json').exists() or not (shard/'status.json').exists():
            raise RuntimeError('Collected native shard incomplete or failed '+str(shard))
    logs=execution/f'{stage}_{job}';logs.mkdir(exist_ok=True)
    for index in record['indices']:
        (logs/f'shard_{index}.log').write_text(command(['ssh','einst',f'cat {REMOTE}/slurm-v51-{job}_{index}.log']))
    record['accounting']=command(['ssh','einst',f'sacct -j {job} --format=JobID,State,ExitCode,Elapsed,MaxRSS --noheader'])
    record['collection_retry_reason']='Transient SSH connection reset; no simulation resubmitted'
    record['resource_retry_indices']=[];write_json(path,attempts)
    print('Collected existing completed job',job,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('heldout','calibration','history','collect-heldout'))
    a=p.parse_args()
    if a.stage=='history':
        archive_history()
    elif a.stage=='collect-heldout':
        collect_existing('heldout')
    else:
        batch(a.stage)
