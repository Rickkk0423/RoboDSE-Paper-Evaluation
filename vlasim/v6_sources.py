"""Archive literature discovery evidence and observed retrieval limitations."""
from pathlib import Path
import shutil

from v6_common import ROOT,load,write_json,digest


def run():
    out=ROOT/'cost/sources/discovery';out.mkdir(exist_ok=True)
    artifacts=[]
    for name in ('lp_arxiv.xml','gddr_arxiv.xml','fg.xml','neupims.xml','drampower_tree.json','dramsys_tree.json',
                 'nvsearch.html','nv2017.html','fgpage.html','ram.html','darwin.pdf','darwin.txt','lpddr_phy.html'):
        source=Path('/tmp')/('v6_'+name)
        if source.exists():
            target=out/name;shutil.copy2(source,target)
            artifacts.append(dict(path=str(target),sha256=digest(target),bytes=target.stat().st_size))
    records=[
        dict(url='https://people.csail.mit.edu/sanchez/papers/2021.f1.isca.pdf',result='HTTP404',
             resolution='Actual venue MICRO; author2021.f1.micro.pdf retrieved and archived.'),
        dict(url='https://www.rambus.com/wp-content/uploads/2020/06/Rambus-HBM2E-and-GDDR6-whitepaper.pdf',result='HTTP404'),
        dict(url='https://www.rambus.com/wp-content/uploads/2020/04/Rambus-HBM2E-GDDR6-White-Paper.pdf',result='HTTP404'),
        dict(url='https://www.rambus.com/hbm2e-and-gddr6-memory-solutions-for-ai/',result='Redirected to WordPress login HTML; no public numerical whitepaper content obtained'),
        dict(url='https://research.nvidia.com/publication/2017-10_fine-grained-dram-energy-efficient-dram',result='HTTP404'),
        dict(url='https://research.nvidia.com/publication/2017-10_fine-grained-dram-energy-efficient-dram-future-gpus',result='HTTP404'),
        dict(url='https://research.nvidia.com/sites/default/files/pubs/2017-10_Fine-Grained-DRAM%3A-Energy-Efficient/FGDRAM.pdf',result='HTTP404',
             resolution='Public NVIDIA publications search found correct title and author-hosted CloudFront manuscript; retrieved.'),
        dict(doi='10.1109/EPEPS63858.2025.11346715',title='8.4GT/s LPDDR5x and 6.4GT/s DDR5 Combo PHY',
             result='Crossref metadata only; publisher numerical content not retrieved/verified. No area/energy number adopted.'),
        dict(doi='10.1109/ISSCC.2018.8310255',
             result='Title/abstract metadata not sufficient for whole-memory energy or logic PHY area; no guessed7.5pJ number adopted.'),
        dict(doi='10.1109/ISSCC.2014.6757323',result='Horowitz primary PDF attempts unavailable; no remembered coefficients adopted.'),
        dict(tool='web.run',result='Search calls returned empty results; no usable search-result citations invented.'),
        dict(source='LP-Spec arXiv2508.07227v3',result='Verified LPDDR5 timing/area-overhead paper, no isolated PHY area or per-bit energy found; not used as missing coefficient.'),
        dict(source='NeuPIMs arXiv2403.00579v3',result='Aggregate system power/DDR3-based power model is not compatible per-type LPDDR5/GDDR6 energy; not substituted.'),
        dict(source='DRAMPower and DRAMSys official source tree',result='LPDDR5/HBM2 command-level models are available, not a matched GDDR6 PHY-area dataset; no unexecuted tool result claimed.'),
    ]
    write_json(out/'status.json',dict(date='2026-11-16',records=records,artifacts=artifacts,
        scope='Observed discovery/retrieval limitations; earlier unsuccessful speculative URL probes do not establish publication absence. '
            'Sources may exist outside the accessible set. Missing inputs are a provenance blocker, not zero cost.'))
    write_json(ROOT/'cost/external_input_request.json',dict(status='required_before_global_cost_selection',
        inputs=['A_phy_LPDDR5 mm2 per16-bit channel at known node/bandwidth',
            'A_phy_GDDR6 mm2 per16-bit channel at known node/bandwidth',
            'e_dram_LPDDR5 pJ/bit including stated DRAM+I/O scope',
            'e_dram_GDDR6 pJ/bit including stated DRAM+I/O scope'],
        required_metadata=['primary source URL/DOI and exact table/page','process node and voltage',
            'channel width, rate and controller/PHY scope','central estimate and defensible uncertainty interval',
            'conversion rule to target hardware; no unsupported cross-type reuse'],
        not_required_to_continue_B_C='These tasks have independent completed evidence; only A/D/E global-cost closure depends on inputs.'))
    write_json(ROOT/'execution/implementation_failures.json',dict(observed=[
        dict(stage='seq preparation',failure='Initial KeyError: seq assumed per-item, actual frozen input uses global seq_traces.',
            resolution='Corrected before frozen100-identity manifest; failed empty output directory reused, no prior artifacts removed.'),
        dict(stage='local native collector',failure="AttributeError: str has no attribute read_bytes at digest(__file__)",
            evidence='results/v6/seq_local/shard_0/failure.json',
            resolution='digest(Path(__file__)) before remote campaign; successful cross-host controls are separate shard1/91 directories.'),
        dict(stage='synthesis preparation',failure='Initial guessed INVBUF Liberty filename unavailable.',
            resolution='Used official repository listing; actual220122 INVBUF and220123 SEQ source files archived.'),
        dict(stage='synthesis collection',failure='Yosys $scopeinfo metadata was initially treated as an unmapped cell.',
            evidence='results/v6/cost/synth/v6_pe.prior_0.log',
            resolution='Ignore metadata only; all actual unmapped logic still fatal. Successful netlists and mapped-cell areas archived.'),
        dict(stage='band independent L/S audit',failure='Blank config_id aliased same-allocation control engine cache across k.',
            evidence='results/v6/execution/finish/attempt_0/05_audit_band.log',
            resolution='All11200 control inputs rerun with full semantic keys in band/control_repair; original frozen raw evidence '
                'and initial summaries preserved. All21580 nonblank-ID frontier inputs unaffected. New regression test covers blank-ID k1/2/3.'),
        dict(stage='plot layout QA',failure='Canvas-bounds check included an out-of-view auto tick1.2 which Matplotlib does not render.',
            evidence='results/v6/execution/finish/attempt_1/16_plots.log',
            resolution='Exclude tick artists outside axis view intervals; actual visible labels still checked. Prior executed sources archived in attempt1.'),
        ],scope='Known implementation failures retained/disclosed; native unsupported variants and literature retrieval gaps have their own full tables.'))


if __name__=='__main__':run()
