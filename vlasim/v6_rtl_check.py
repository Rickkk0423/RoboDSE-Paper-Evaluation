"""Small RTL wrapper sanity check; not an exhaustive floating-point verification."""
from pathlib import Path
import subprocess

from v6_common import ROOT,write_json,digest


def run(out=None):
    out=Path(out) if out else ROOT/'cost/synth/rtl_check'
    out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'cost/synth/HardFloat-1/source'
    rtl=[source/name for name in ('HardFloat_primitives.v','HardFloat_rawFN.v','RISCV/HardFloat_specialize.v',
        'isSigNaNRecFN.v','fNToRecFN.v','recFNToFN.v','mulAddRecFN.v','addRecFN.v')]
    cmd=['iverilog','-g2012','-I'+str(source),'-I'+str(source/'RISCV'),'-s','v6_rtl_tb',
        '-o',str(out/'sim.vvp'),*map(str,rtl),'vlasim/v6_pe.v','vlasim/v6_rtl_tb.v']
    compile_result=subprocess.run(cmd,capture_output=True,text=True)
    (out/'compile.log').write_text(compile_result.stdout+compile_result.stderr)
    compile_result.check_returncode()
    result=subprocess.run(['vvp',str(out/'sim.vvp')],capture_output=True,text=True)
    (out/'run.log').write_text(result.stdout+result.stderr);result.check_returncode()
    if 'PASS:' not in result.stdout:raise RuntimeError('RTL sanity check did not complete')
    write_json(out/'status.json',dict(passed=True,command=cmd,scope='Five finite exact PE cases plus one vector add; '
        'checks operand expansion and register latency only, not exhaustive BF16 rounding/NaN/subnormal behavior or timing closure.',
        source_sha256={p:digest(p) for p in ('vlasim/v6_pe.v','vlasim/v6_rtl_tb.v')},
        hashes={name:digest(out/name) for name in ('sim.vvp','compile.log','run.log')}))


if __name__=='__main__':run()
