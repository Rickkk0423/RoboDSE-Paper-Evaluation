"""Run V7 phases in order, retaining logs, executed sources and every pytest result."""
from pathlib import Path
import shutil
import subprocess
import sys
import time
import os

from v7_common import ROOT, load, write_json, digest


def step(name, args, outputs=()):
    out = ROOT / 'execution' / name
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'status.json').exists():
        saved = load(out / 'status.json')
        if saved['returncode'] == 0:
            print('Completed stage retained:', name, flush=True)
            return
        raise RuntimeError('Prior failed stage retained; fix and run a new attempt directory: ' + name)
    sources = out / 'executed_sources'
    sources.mkdir(exist_ok=True)
    for p in Path('vlasim').glob('v7_*.py'):
        shutil.copy2(p, sources / p.name)
    started = time.time()
    env = dict(os.environ, PYTHONPATH='vlasim', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    command = [sys.executable, *args]
    print('Running stage', name, ' '.join(command), flush=True)
    with (out / 'stdout.log').open('w') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, env=env)
    write_json(out / 'status.json', dict(command=command, started=started, ended=time.time(),
        returncode=result.returncode, log_sha256=digest(out / 'stdout.log'),
        executed_sources={p.name: digest(p) for p in sources.iterdir()},
        output_sha256={str(p): digest(p) for p in map(Path, outputs) if p.is_file()}))
    print('Finished stage', name, 'exit', result.returncode, flush=True)
    if result.returncode:
        raise RuntimeError('Stage failed: ' + name + '; see ' + str(out / 'stdout.log'))


def tests(number, name):
    step(number + '_pytest_' + name,
         ['-m', 'pytest', '-q', '--junitxml=' + str(ROOT / 'validation' / (number + '_' + name + '.xml'))])


def run():
    step('03_secondary_pre', ['vlasim/v7_secondary.py', 'pre_recheck'])
    tests('03', 'secondary')
    step('04_figdata_pre', ['vlasim/v7_figdata.py', 'pre_recheck'])
    tests('04', 'figdata')
    step('05_recheck', ['vlasim/v7_validate.py', 'recheck', '--workers', '4'])
    step('05_pareto_post', ['vlasim/v7_pareto.py', 'post_recheck'])
    step('05_secondary_post', ['vlasim/v7_secondary.py', 'post_recheck'])
    step('05_figdata_post', ['vlasim/v7_figdata.py', 'post_recheck'])
    step('05_stress', ['vlasim/v7_validate.py', 'stress', '--workers', '4'])
    tests('05', 'validation')
    step('06_task', ['vlasim/v7_task.py'])
    tests('06', 'task')
    step('07_preview', ['vlasim/v7_figdata.py', 'preview'])
    step('07_report', ['vlasim/v7_report.py', 'publish'])
    tests('07', 'final')
    step('08_publish', ['vlasim/v7_report.py', 'publish'])
    step('08_verify', ['vlasim/v7_report.py', 'verify'])


if __name__ == '__main__':
    run()
