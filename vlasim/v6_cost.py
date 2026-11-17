"""Traceable partial cost estimates; unknown external coefficients stay null."""
import shutil
from pathlib import Path

import numpy as np

from v6_common import ROOT,OLD,load,write_json,write_csv,digest
from v51_package import read_csv
from vlasim.workload import Pi05Workload


def coefficient(value,lower,upper,unit,source,conversion,**extra):
    return dict(value=value,lower=lower,upper=upper,points=[lower,value,upper],unit=unit,
        status='literature_estimate' if value is not None else 'missing_external_input',
        node_nm=7,source=source,conversion=conversion,**extra)


def prepare():
    out=ROOT/'cost';sources=out/'sources';sources.mkdir(parents=True,exist_ok=True)
    archived=[]
    for name,url in (('f1','https://people.csail.mit.edu/sanchez/papers/2021.f1.micro.pdf'),
                     ('f1_extended','https://arxiv.org/pdf/2109.05371v2'),
                     ('lpspec','https://arxiv.org/pdf/2508.07227v3'),
                     ('neupims','https://arxiv.org/pdf/2403.00579v3'),
                     ('fgdram','https://d1qx31qr3h6wln.cloudfront.net/publications/MICRO_2017_Fine_Grained_DRAM.pdf')):
        for extension in ('pdf','txt'):
            source=Path('/tmp')/f'v6_{name}.{extension}'
            if source.exists():
                target=sources/f'{name}.{extension}';shutil.copy2(source,target)
                archived.append(dict(path=str(target),sha256=digest(target),url=url,retrieved='2026-11-16'))
    synth=load(out/'synth/summary.json');pe=synth['results']['v6_pe'];vector=synth['results']['v6_vector_lane']
    base=(16384*pe['cell_area_um2']+32*vector['cell_area_um2'])/1e6
    f1=dict(title='F1: A Fast and Programmable Accelerator for Fully Homomorphic Encryption',
        doi='10.1145/3466752.3480070',url='https://people.csail.mit.edu/sanchez/papers/2021.f1.micro.pdf',
        location='Table 2, Section 7: 14/12nm commercial process; 16x4MB scratchpad 48.09mm2/20.35W; '
            'three networks 10.02mm2; two HBM2 PHYs 29.80mm2, each 512GB/s.')
    tool=dict(tool='Yosys/ABC + official Berkeley HardFloat + ASAP7 RVT TT predictive library',
        url='https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/platforms/asap7',
        evidence='results/v6/cost/synth/summary.json',sha256=digest(out/'synth/summary.json'))
    # F1 uses MB without explicitly defining binary/decimal units: include both in the bounds.
    sram_mid=48.09/64*(7/13)**2
    c={
        'A_core':coefficient(base*1.35,base*1.1,base*1.6,'mm2/core',tool,
            f'({16384} PEs x {pe["cell_area_um2"]} um2 + 32 FP32 add lanes x {vector["cell_area_um2"]} um2)/1e6 '
            'times analyst-assumed placement/control factors 1.1/1.35/1.6. Includes PE operand/accumulator/output registers; '
            'private SRAM accounted separately. No SRAM local buffer duplication.',
            target_frequency_hz=1e9,timing_closed=False,physical_design=False),
        'a_sram':coefficient(sram_mid,48.09/(64*2**20/1e6)*(7/14)**2*.75,
            48.09/64*(7/12)**2*1.5,'mm2/decimal_MB',f1,
            '48.09mm2 / 64MB x (7/13)^2. Bounds include source MB ambiguity, 12-14nm baseline '
            'and analyst macro/periphery multipliers 0.75-1.5; SRAM area L^2 scaling is an estimate.'),
        'A_misc':coefficient(10.02*(7/13)**2*.5,10.02*(7/14)**2*.25,
            10.02*(7/12)**2,'mm2/design',f1,
            'Fixed 16-port NoC proxy: source 10.02mm2 for 3 networks, geometric L^2 scaling; '
            'analyst-assumed width/complexity factors .25/.5/1. Not a synthesized target NoC.'),
        'e_mac':coefficient(pe['full_toggle_capacitive_energy_pJ']*.3*1.5,
            pe['full_toggle_capacitive_energy_pJ']*.1,pe['full_toggle_capacitive_energy_pJ']*.5*3,
            'pJ/MAC',tool,'Sum mapped PE input-pin capacitance x 0.7V^2; analyst toggle factors .1/.3/.5 '
            'and overhead 1/1.5/3. No workload activity/internal/glitch/clock/routed energy measurement; broad proxy only.'),
        'e_sram':coefficient(20.35/(16*512*2e9)*1e12*(7/13),
            20.35/(16*512*2e9)*1e12*(7/14)*.5,
            20.35/(16*512*2e9)*1e12*2,'pJ/byte',f1,
            'Source scratchpad TDP divided by 16 banks x512B x2GHz; capacitance linear L scaling, '
            'voltage scaling unknown and left unity. Aggregate TDP/access proxy, not isolated access energy. NOT USED: '
            'SRAM access bytes absent from simulator.'),
        'leakage_density':coefficient(pe['cell_leakage_density_W_mm2_quantiles'][1]*.5,
            pe['cell_leakage_density_W_mm2_quantiles'][0]*.3,
            pe['cell_leakage_density_W_mm2_quantiles'][2]*.7,'W/mm2',tool,
            'ASAP7 Liberty cell leakage_power in pW / cell area converted to W/mm2; cell density '
            'p5/p50/p95 times assumed utilization .3/.5/.7. Not measured chip static power.'),
    }
    for standard,bits,gbps in (('LPDDR5',16,12.8),('GDDR6',16,28.),('HBM2',128,32.)):
        if standard=='HBM2':
            value=29.8/1024*gbps
            c['A_phy_'+standard]=coefficient(value*(7/13)**2,value*(7/14)**2,value,
                'mm2/channel',f1,'29.80mm2 / (2 x512GB/s) x32GB/s/channel. Central digital L^2 '
                'scaling; upper leaves analog PHY unscaled, lower uses14nm geometric scaling. '
                'The source node is12-14nm; analog scaling is not assured.',source_node_nm=[12,14])
        else:
            c['A_phy_'+standard]=coefficient(None,None,None,'mm2/channel',
                dict(reason='No accessible primary numerical PHY-area source verified; no cross-type reuse.'),
                'No conversion performed; cannot assume zero or borrow HBM PHY density.')
        c['e_dram_'+standard]=coefficient(None,None,None,'pJ/bit',
            dict(reason='No verified whole-memory per-bit energy at compatible scope obtained.'),
            'Do not substitute PHY-only power, DRAM die area, or an uncited remembered number.',
            dram_process_node_nm=None,scope='external DRAM+I/O energy, not geometrically scaled with logic node')
        c['e_dram_'+standard]['node_nm']=None
    c['e_dram_HBM2']=coefficient(3.92,3.92*.5,3.97*1.5,'pJ/bit',
        dict(title='Fine-Grained DRAM: Energy-Efficient DRAM for Extreme Bandwidth Systems',
            doi='10.1145/3123939.3124545',
            url='https://research.nvidia.com/publication/2017-10_fine-grained-dram-energy-efficient-dram-extreme-bandwidth-systems',
            pdf='https://d1qx31qr3h6wln.cloudfront.net/publications/MICRO_2017_Fine_Grained_DRAM.pdf',
            location='Section2.1/Figure1: 1.21pJ activation +2.24pJ on-die movement +0.3pJ external I/O; '
                '3.92pJ/bit total with ECC overhead, introduction states3.97pJ/bit.'),
        'Use Section2 total3.92pJ/bit, not0.3pJ PHY-only. Bounds are analyst0.5-1.5x envelope also covering '
        'the source3.92/3.97 textual difference. Workload/locality/device/clock transfer remains unvalidated; '
        'external DRAM process is not scaled with target7nm logic.')
    c['e_dram_HBM2']['node_nm']=None
    c['P_static']=coefficient(None,None,None,'W/design',tool,
        'Derived per design as Area x leakage_density; unavailable where total area has missing PHY inputs. '
        'Supplemental only, not added to the primary MAC+DRAM accounting.')
    c['P_static']['status']='derived_per_design_literature_estimate'
    write_json(out/'sources/manifest.json',dict(artifacts=archived,synthesis_sources=load(out/'synth/sources.json')))
    write_json(out/'coefficients.json',dict(status='partial_literature_estimate_external_inputs_missing',
        coefficients=c,area_formula='cores*A_core+(shared_MB+cores*private_MB)*a_sram+A_phy(type,channels)+A_misc',
        energy_formula='MACs*e_mac+SRAM_bytes*e_sram+DRAM_bytes*8*e_dram(type)+P_static*T',
        primary_energy_scope='MAC + DRAM only when both coefficients exist. SRAM access traffic uninstrumented; '
            'static omitted per specification fallback, separately available symbolically.',
        target_node_nm=7,known_area_components='core+shared/private SRAM+misc; HBM2 also has estimated PHY',
        blocked_inputs=['A_phy_LPDDR5','A_phy_GDDR6','e_dram_LPDDR5','e_dram_GDDR6'],
        assumptions='Numerical assumptions are explicit conversion uncertainties, never external measurements.'))
    draws(c)


def draws(coefficients=None):
    c=coefficients or load(ROOT/'cost/coefficients.json')['coefficients'];keys=[k for k,v in c.items() if v['value'] is not None]
    rng=np.random.default_rng(20261116)
    samples=np.array([rng.uniform(c[k]['lower'],c[k]['upper'],2000) for k in keys]).T
    np.savez_compressed(ROOT/'cost/draws.npz',samples=samples,keys=np.array(keys))
    write_json(ROOT/'cost/sampling.json',dict(samples=2000,seed=20261116,distribution='independent uniform',
        shared_draws_across_designs=True,coefficient_keys=keys,
        missing_keys=[k for k,v in c.items() if v['status']=='missing_external_input'],
        full_cost_MC_available=False,known_component_only=True,
        three_point_method='Per-coefficient low/mid/high one-at-a-time plus all-low/all-mid/all-high; '
            'positive linear costs have exact extrema at low/high corners. Not full 3^N enumeration.',
        draws_sha256=digest(ROOT/'cost/draws.npz')))
    scenarios=[]
    for level in ('lower','value','upper'):
        scenarios.append(dict(id='all_'+level,**{k:c[k][level] for k in keys}))
    for k in keys:
        for level in ('lower','value','upper'):
            scenarios.append(dict(id=k+'_'+level,**{j:c[j][level if j==k else 'value'] for j in keys}))
    write_csv(ROOT/'cost/three_point_scenarios.csv',scenarios)


def feature(row):
    return np.array([float(row['n_cores']),float(row['sram_mb'])+float(row['n_cores'])*float(row['local_kb'])*1024/1e6,1.])


def estimate(row,c=None):
    c=c or load(ROOT/'cost/coefficients.json')['coefficients'];x=feature(row)
    memory=row['memory'];standard=memory.split('_')[0];channels=int(memory.split('_c')[-1])
    values={}
    for bound in ('lower','value','upper'):
        partial=float(x@np.array([c[k][bound] for k in ('A_core','a_sram','A_misc')]))
        phy=c['A_phy_'+standard][bound]
        values['known_components_area_'+bound+'_mm2']=partial
        values['area_'+bound+'_mm2']=partial+channels*phy if phy is not None else None
    wl=Pi05Workload();macs=(wl.vlm_totals()[0]+wl.dit_totals_per_request()[0])/2
    traffic=row.get('steady_dram_GB_per_req') or row.get('dram_GB_per_req')
    values.update(MACs_per_req=macs,DRAM_bytes_per_req=float(traffic)*1e9 if traffic else None,
        energy_lower_mJ=None,energy_value_mJ=None,energy_upper_mJ=None,
        energy_status='missing_external_e_dram; SRAM traffic uninstrumented',
        area_status='literature_estimate' if values['area_value_mm2'] is not None else 'partial_missing_PHY',
        MAC_only_lower_mJ=macs*c['e_mac']['lower']*1e-9,MAC_only_value_mJ=macs*c['e_mac']['value']*1e-9,
        MAC_only_upper_mJ=macs*c['e_mac']['upper']*1e-9)
    period=row.get('T_s') or row.get('Tmin_s')
    for bound in ('lower','value','upper'):
        area=values['area_'+bound+'_mm2']
        values['static_'+bound+'_W']=area*c['leakage_density'][bound] if area is not None else None
        values['static_energy_'+bound+'_mJ']=area*c['leakage_density'][bound]*float(period)*1000 if area is not None and period else None
        dram=c['e_dram_'+standard][bound]
        if dram is not None and traffic:
            values['energy_'+bound+'_mJ']=(macs*c['e_mac'][bound]+float(traffic)*1e9*8*dram)*1e-9
            values['energy_status']='literature_estimate_MAC_plus_DRAM_only; SRAM/static omitted as permitted'
    return values


def evaluate_frozen():
    c=load(ROOT/'cost/coefficients.json')['coefficients'];rows=[]
    with np.load(ROOT/'cost/draws.npz') as data:
        keys=list(data['keys']);samples=data['samples']
    matrix=samples[:,[keys.index(k) for k in ('A_core','a_sram','A_misc')]]
    for row in read_csv(OLD/'attainable.csv'):
        draws_known=matrix@feature(row)
        standard=row['memory'].split('_')[0]
        full_area=draws_known+int(row['memory'].split('_c')[-1])*samples[:,keys.index('A_phy_HBM2')] if standard=='HBM2' else None
        entry=dict(config_id=row['config_id'],T_s=row['T_s'],hardware_id=row['hardware_id'],
            model=row['model'],track=row['track'],scenario=row['scenario'],**estimate(row,c),
            known_components_MC_p5_mm2=float(np.quantile(draws_known,.05)),
            known_components_MC_p50_mm2=float(np.quantile(draws_known,.5)),
            known_components_MC_p95_mm2=float(np.quantile(draws_known,.95)),
            full_energy_MC_status='blocked_missing_external_inputs',
            propagation_scope='All 21580 frozen frontiers including later excluded tiers; cost coverage is not paper eligibility.')
        entry.update({f'area_MC_p{p}_mm2':float(np.quantile(full_area,p/100)) if full_area is not None else None for p in (5,50,95)})
        if standard=='HBM2':
            energy=(entry['MACs_per_req']*samples[:,keys.index('e_mac')]+entry['DRAM_bytes_per_req']*8*samples[:,keys.index('e_dram_HBM2')])*1e-9
            entry.update({f'energy_MC_p{p}_mJ':float(np.quantile(energy,p/100)) for p in (5,50,95)})
            entry['full_energy_MC_status']='MAC_plus_DRAM_literature_estimate_no_SRAM_or_static'
        rows.append(entry)
    write_csv(ROOT/'cost/frozen_frontier_costs.csv',rows)
    write_json(ROOT/'cost/status.json',dict(frontier_rows=len(rows),samples=2000,
        area_complete_rows=sum(r['area_status']=='literature_estimate' for r in rows),
        energy_complete_rows=sum(r['energy_value_mJ'] is not None for r in rows),
        full_cost_ranking_status='BLOCKED_missing_external_coefficients',
        source_sha256=digest(__file__),coefficients_sha256=digest(ROOT/'cost/coefficients.json')))


if __name__=='__main__':
    prepare();evaluate_frozen()
