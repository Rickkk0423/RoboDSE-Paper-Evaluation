"""Independently parse and render native VSDX pages through libvisio."""
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as E
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'paper/evaluation_delivery'


def run():
    path=OUT/'RoboDSE_Evaluation.vsdx'
    text=subprocess.check_output(['vsd2text',str(path)],text=True)
    for value in ['47.28%','16,416','82,070','no batching']:
        assert value in text,value
    xhtml=subprocess.check_output(['vsd2xhtml',str(path)])
    (OUT/'visio_render.xhtml').write_bytes(xhtml)
    root=E.fromstring(xhtml)
    svgs=[r for r in root.iter() if r.tag.split('}')[-1]=='svg']
    assert len(svgs)==3,len(svgs)
    pages=[]
    for i,svg in enumerate(svgs,1):
        target=OUT/f'visio_page_{i}.svg'
        target.write_bytes(E.tostring(svg))
        subprocess.run(['rsvg-convert','-w','1620','-o',str(OUT/f'visio_page_{i}.png'),str(target)],check=True)
        pages.append(dict(page=i,rendered=True))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for name in z.namelist():
            if name.endswith('.xml') or name.endswith('.rels'):E.fromstring(z.read(name))
        natives=[]
        for i in range(1,4):
            page=E.fromstring(z.read(f'visio/pages/page{i}.xml'))
            shapes=page.findall('.//{http://schemas.microsoft.com/office/visio/2012/main}Shape')
            assert not page.findall('.//{http://schemas.microsoft.com/office/visio/2012/main}ForeignData')
            natives.append(len(shapes))
    (OUT/'visio_validation.json').write_text(json.dumps(dict(zip_valid=True,xml_valid=True,
        native_shapes_per_page=natives,independent_parser='libvisio vsd2text/vsd2xhtml',
        rendered_pages=pages,microsoft_visio_app_open_test=False),indent=2)+'\n')
    print('Native VSDX parsed and rendered:',natives)


if __name__=='__main__':run()
