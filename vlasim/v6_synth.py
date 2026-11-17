"""ASAP7 predictive-library synthesis; no physical-design or silicon calibration claim."""
import gzip
import shutil
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
from liberty.parser import parse_liberty

from v6_common import ROOT,load,write_json,digest

BASE='https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/asap7/lib/NLDM/'


def prepare():
    out=ROOT/'cost/synth';out.mkdir(parents=True,exist_ok=True)
    records=[];libraries=[]
    names=[f'asap7sc7p5t_{group}_RVT_TT_nldm_211120.lib.gz' for group in ('SIMPLE','AO','OA')]
    names+=['asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib.gz','asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib']
    for name in names:
        path=out/name
        if not path.exists():
            urllib.request.urlretrieve(BASE+name,path)
        libraries.append(parse_liberty(gzip.open(path,'rt').read() if path.suffix=='.gz' else path.read_text()))
        records.append(dict(path=str(path),url=BASE+name,sha256=digest(path)))
    combined=libraries[0];seen={(g.group_name,str(g.args)) for g in combined.groups}
    for library in libraries[1:]:
        for group in library.groups:
            key=group.group_name,str(group.args)
            if key not in seen:
                combined.groups.append(group);seen.add(key)
    (out/'asap7_merged.lib').write_text(str(combined))
    records.append(dict(path='HardFloat-1',url='https://www.jhauser.us/arithmetic/HardFloat-1.zip',
        source_files_sha256={str(p.relative_to(out)):digest(p) for p in (out/'HardFloat-1/source').rglob('*') if p.is_file()}))
    write_json(out/'sources.json',records)
    return out


def run():
    out=prepare();source=out/'HardFloat-1/source'
    rtl=[source/name for name in ('HardFloat_primitives.v','HardFloat_rawFN.v','RISCV/HardFloat_specialize.v',
        'isSigNaNRecFN.v','fNToRecFN.v','recFNToFN.v','mulAddRecFN.v','addRecFN.v')]
    synth={}
    for top in ('v6_pe','v6_vector_lane'):
        script=f'read_verilog -I{source} -I{source}/RISCV '+ ' '.join(map(str,rtl))+ ' vlasim/v6_pe.v\n'+\
            f'synth -top {top} -flatten\ndfflibmap -liberty {out}/asap7_merged.lib\n'+\
            f'abc -liberty {out}/asap7_merged.lib -D 1000\nclean\n'+\
            f'stat -liberty {out}/asap7_merged.lib\nwrite_json {out}/{top}.json\n'
        (out/(top+'.ys')).write_text(script)
        log=out/(top+'.log')
        if log.exists():
            backup=out/(top+f'.prior_{len(list(out.glob(top+".prior_*.log")))}.log')
            shutil.copy2(log,backup)
        with log.open('w') as stream:
            subprocess.run(['.venv/bin/yowasp-yosys','-s',str(out/(top+'.ys'))],stdout=stream,stderr=subprocess.STDOUT,check=True)
        net=load(out/(top+'.json'));cells=net['modules'][top]['cells']
        library=parse_liberty((out/'asap7_merged.lib').read_text())
        lookup={str(c.args[0]):c for c in library.get_groups('cell')}
        areas=[];cap=[];density=[]
        for cell in cells.values():
            name=cell['type']
            if name=='$scopeinfo':
                continue
            if name not in lookup:
                raise RuntimeError('Unmapped synthesis cell '+name)
            char=lookup[name];area=float(char['area']);areas.append(area)
            capacitance=sum(float(pin.get_attribute('capacitance') or 0.) for pin in char.get_groups('pin'))
            cap.append(capacitance)
            leak=[float(g['value']) for g in char.get_groups('leakage_power') if float(g['value'])>0]
            if leak:
                density.append(float(np.mean(leak))*1e-12/area*1e6)
        # Supply charging of characterized input capacitance, activity range left explicit.
        # Does not claim glitch/clock/route power or CACTI-equivalent SRAM energy.
        energy_fJ=sum(cap)*.7**2
        synth[top]=dict(mapped_cells=len(cells),cell_area_um2=sum(areas),input_capacitance_fF=sum(cap),
            full_toggle_capacitive_energy_pJ=energy_fJ/1000,
            cell_leakage_density_W_mm2_quantiles=list(map(float,np.quantile(density,[.05,.5,.95]))),
            netlist_sha256=digest(out/(top+'.json')),log_sha256=digest(log))
    write_json(out/'summary.json',dict(status='literature_estimate',node_nm=7,library='ASAP7 7.5T RVT TT predictive',
        target_frequency_hz=1e9,frequency_achieved=None,physical_design_run=False,
        scope='HardFloat BF16-expanded operands with FP32 FMA and PE input/output registers, separate FP32 vector lane. '
            'ABC 1000ps target, no timing closure or routing. Extrapolate 16384 PEs + 32 vector lanes, add area uncertainty '
            'for clock/control/interconnect. Input-capacitance switching proxy excludes internal short-circuit/glitches '
            'and routed clock tree; broad energy interval is an assumption, not calibrated energy.',results=synth,
        tool_version=subprocess.run(['.venv/bin/yowasp-yosys','-V'],capture_output=True,text=True,check=True).stdout,
        wrapper_sha256=digest('vlasim/v6_pe.v'),sources_sha256=digest(out/'sources.json')))
    print(synth,flush=True)


if __name__=='__main__':
    run()
