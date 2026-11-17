"""Finish all feasible V6 tasks after the24 repaired DSE shards, with stage tests."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from v6_common import ROOT,load,write_json,digest
from v51_package import read_csv


def run(resume_paper=False):
    if len(list((ROOT/'dse/shards').glob('*/status.json')))!=24:
        raise RuntimeError('Wait for all24 DSE shards before final collection')
    if (ROOT/'hard_stop.json').exists():raise RuntimeError('Hard stop must be investigated before continuation')
    attempts=ROOT/'execution/finish';attempts.mkdir(exist_ok=True)
    out=attempts/f'attempt_{len(list(attempts.glob("attempt_*")))}';out.mkdir()
    env=dict(os.environ,PYTHONPATH='vlasim',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    steps=[]
    def call(name,*args):
        cmd=[sys.executable,*args];log=out/(f'{len(steps):02d}_'+name+'.log')
        print('V6 finish:',name,flush=True)
        with log.open('w') as stream:
            result=subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        steps.append(dict(name=name,command=cmd,returncode=result.returncode,log=str(log),sha256=digest(log)))
        write_json(out/'status.json',dict(steps=steps,source_sha256=digest(__file__)))
        if result.returncode:
            print(log.read_text()[-12000:],flush=True)
            raise RuntimeError('Finish stage failed '+name)
    def pytest(stage):call(stage,'-m','pytest','-q','--junitxml='+str(ROOT/'validation'/f'{stage}.xml'))
    if resume_paper:
        gates=['validation/native_audit.json','validation/dse_archive_audit.json','band/audit.json','validation/selected_archive_audit.json']
        if any(not load(ROOT/p)['passed'] for p in gates):raise RuntimeError('Cannot resume failed numerical gates')
        suite=ET.parse(ROOT/'validation/stage_B_control_repair_C_DSE.xml').getroot()
        if any(int(s.get('failures',0))+int(s.get('errors',0)) for s in suite.iter('testsuite')):
            raise RuntimeError('Cannot resume failed stage tests')
        write_json(out/'resume_dependencies.json',{p:digest(ROOT/p) for p in [*gates,'validation/stage_B_control_repair_C_DSE.xml']})
        supplemental=ROOT/'dse/ablation_supplement/status.json';state=load(supplemental)
        if state['adapter_source_sha256']!=digest('vlasim/v6_paper.py'):
            archives=[p for p in attempts.glob('attempt_*/paper_source.py') if digest(p)==state['adapter_source_sha256']]
            if not archives:raise RuntimeError('Executed collector adapter source not preserved')
            write_json(supplemental,dict(state,adapter_source_archive=str(archives[0])))
        call('source_evidence','vlasim/v6_sources.py')
    else:
        call('cost','vlasim/v6_cost.py');call('source_evidence','vlasim/v6_sources.py')
        call('corrected_controls','vlasim/v6_control_band.py')
        call('collect','vlasim/v6_paper.py','collect')
        call('audit_native','vlasim/v6_audit.py','native');call('audit_dse','vlasim/v6_audit.py','dse')
        call('audit_band','vlasim/v6_audit.py','band')
        pytest('stage_B_control_repair_C_DSE')
        call('selection','vlasim/v6_paper.py','selection')
        for round_number in range(12):
            before={r['point_id'] for r in read_csv(ROOT/'paper/selected_conditional_points.csv')}
            call('selected_reference_'+str(round_number),'vlasim/v6_selected.py','recheck')
            call('reselect_'+str(round_number),'vlasim/v6_paper.py','selection')
            after={r['point_id'] for r in read_csv(ROOT/'paper/selected_conditional_points.csv')}
            if before==after and not load(ROOT/'paper/selected_recheck_status.json')['failed']:break
        else:raise RuntimeError('Selected960 refinement did not reach a verified fixed point; all attempts preserved')
        call('selected_stress','vlasim/v6_selected.py','stress')
        call('audit_selected','vlasim/v6_audit.py','selected')
    call('paper_tables','vlasim/v6_paper.py','figures')
    call('parametric_pairs','vlasim/v6_paper.py','parametric')
    call('energy_subset','vlasim/v6_paper.py','energy')
    call('plots','vlasim/v6_figures.py')
    pytest('stage_D_paper')
    call('task_preparation','vlasim/v6_task.py','prepare')
    pytest('stage_E_task')
    call('rtl_wrapper','vlasim/v6_rtl_check.py')
    pytest('final')
    # Close the mutable orchestration log before pinning its own delivery artifact.
    write_json(out/'status.json',dict(status='completed_feasible_steps_before_publication',steps=steps,source_sha256=digest(__file__)))
    for action in ('publish','verify'):
        subprocess.run([sys.executable,'vlasim/v6_report.py',action],env=env,check=True)
    print('V6 feasible delivery complete; external cost blockers explicit.',flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--resume-paper',action='store_true');a=p.parse_args()
    run(a.resume_paper)
