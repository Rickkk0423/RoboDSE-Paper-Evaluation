import csv
import json
from pathlib import Path
import posixpath
import zipfile
import xml.etree.ElementTree as E

import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_visio_package_has_native_shapes_and_resolved_relationships():
    path=ROOT/'paper/evaluation_delivery/RoboDSE_Evaluation.vsdx'
    if not path.exists():pytest.skip('Build the delivery first')
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        for name in names:
            if name.endswith('.rels'):
                base='' if name=='_rels/.rels' else name.split('/_rels/')[0]
                for rel in E.fromstring(z.read(name)):
                    assert posixpath.normpath(posixpath.join(base,rel.get('Target'))) in names
        for i in (1,2,3):
            page=E.fromstring(z.read(f'visio/pages/page{i}.xml'))
            ns={'v':'http://schemas.microsoft.com/office/visio/2012/main'}
            assert len(page.findall('.//v:Shape',ns))>50
            assert not page.findall('.//v:ForeignData',ns)


def test_primary_case_is_balanced_and_unpruned():
    directory=ROOT/'results/v8_no_batching_case_final'
    if not (directory/'summary.json').exists():pytest.skip('Run primary case first')
    summary=json.loads((directory/'summary.json').read_text())
    assert summary['configurations']==128
    assert not summary['incumbent_pruning']
    assert not summary['failed_960_checks']
    with (directory/'configurations.csv').open() as f:rows=list(csv.DictReader(f))
    for hardware in {r['hardware_id'] for r in rows}:
        subset=[r for r in rows if r['hardware_id']==hardware]
        assert len(subset)==16
        assert sum(r['mode']=='serial' for r in subset)==1
        for split in (1,2,3):
            assert {(int(r['k']),r['batching']) for r in subset
                    if r['mode']=='pipelined' and int(r['vlm_cores'])==split}=={
                        (1,'True'),(2,'True'),(3,'True'),(2,'False'),(3,'False')}


def test_frozen_frontier_classification_reproduced():
    directory=ROOT/'results/v8_no_batching'
    if not directory.exists():pytest.skip('Run selection ablation first')
    with (directory/'box_comparisons.csv').open() as f:rows=list(csv.DictReader(f))
    selected={(r['Lmax_ms'],r['Smax_ms']):r['relation'] for r in rows
        if r['scope']=='frozen_retained' and r['eligibility']=='all_v7_eligible'
        and r['dimensions']=='cores_BW' and r['baseline']=='serial' and r['alternative']=='full'}
    with (ROOT/'results/v7/paper/pareto_comparison.csv').open() as f:original=list(csv.DictReader(f))
    assert selected=={(r['Lmax_ms'],r['Smax_ms']):r['relation'] for r in original}
