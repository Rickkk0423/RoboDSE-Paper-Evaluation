"""Build editable native Visio figures and SVG previews from frozen CSV data."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as E
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'paper/evaluation_delivery'
REFERENCE = Path('/Users/mr.meeseeks/Desktop/DATE/DATE_version.vsdx')
V = 'http://schemas.microsoft.com/office/visio/2012/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'
BLUE, RED, GRAY, GREEN = '#476e80', '#79463d', '#a8adb2', '#4f7a60'
SOURCES = []


def read(relative):
    path = ROOT / relative
    SOURCES.append(dict(path=relative, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    with path.open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(line for line in f if not line.startswith('#')))


class Page:
    def __init__(self, name, title, height=470):
        self.name, self.width, self.height = name, 1080, height
        self.items = []
        self.text(22, 25, 1036, title, 21, bold=True, align='left')

    def text(self, x, y, w, text, size=15, color='#222222', bold=False, align='center'):
        self.items.append(dict(kind='text', x=x, y=y, w=w, h=size*1.6,
                               text=text, size=size, color=color, bold=bold, align=align))

    def rect(self, x, y, w, h, color, stroke='none', data=None):
        self.items.append(dict(kind='rect', x=x, y=y, w=w, h=h, color=color, stroke=stroke, data=data))

    def line(self, x1, y1, x2, y2, color='#333333', width=1.2, data=None):
        self.items.append(dict(kind='line', x=x1, y=y1, x2=x2, y2=y2, color=color, width=width, data=data))

    def dot(self, x, y, color, radius=4, data=None):
        self.rect(x-radius, y-radius, radius*2, radius*2, color, data=data)

    def axes(self, x, y, w, h, xmax, ymax, xticks, yticks, xlabel, ylabel):
        for t in yticks:
            yy = y+h-h*t/ymax
            self.line(x, yy, x+w, yy, '#e2e2e2', .7)
            self.text(x-48, yy-10, 40, f'{t:g}', 13, align='right')
        self.line(x,y,x,y+h); self.line(x,y+h,x+w,y+h)
        for t in xticks:
            xx=x+w*t/xmax
            self.line(xx,y+h,xx,y+h+4)
            self.text(xx-24,y+h+7,48,f'{t:g}',13)
        self.text(x,y+h+33,w,xlabel,15)
        self.text(x,y-30,w,ylabel,15)
        return lambda a,b:(x+w*a/xmax,y+h-h*b/ymax)

    def svg(self):
        body=[]
        for i in self.items:
            if i['kind']=='text':
                anchor={'left':'start','center':'middle','right':'end'}[i['align']]
                x=i['x']+({'left':0,'center':.5,'right':1}[i['align']])*i['w']
                body.append(f'<text x="{x}" y="{i["y"]+i["size"]}" text-anchor="{anchor}" font-size="{i["size"]}" fill="{i["color"]}" font-weight="{"bold" if i["bold"] else "normal"}">{escape(i["text"])}</text>')
            elif i['kind']=='rect':
                body.append(f'<rect x="{i["x"]}" y="{i["y"]}" width="{i["w"]}" height="{i["h"]}" fill="{i["color"]}" stroke="{i["stroke"]}"/>')
            else:
                body.append(f'<line x1="{i["x"]}" y1="{i["y"]}" x2="{i["x2"]}" y2="{i["y2"]}" stroke="{i["color"]}" stroke-width="{i["width"]}"/>')
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}"><rect width="100%" height="100%" fill="white"/><g font-family="Times New Roman, serif">'+''.join(body)+'</g></svg>'

    def xml(self):
        root=E.Element(f'{{{V}}}PageContents')
        shapes=E.SubElement(root,f'{{{V}}}Shapes')
        def cell(parent,n,v):
            E.SubElement(parent,f'{{{V}}}Cell',N=n,V=str(v))
        for number,i in enumerate(self.items,1):
            s=E.SubElement(shapes,f'{{{V}}}Shape',ID=str(number),Type='Shape',NameU=f'{i["kind"]}.{number}',LineStyle='0',FillStyle='0',TextStyle='0')
            line=i['kind']=='line'
            x=min(i['x'],i['x2']) if line else i['x']
            y=min(i['y'],i['y2']) if line else i['y']
            w=max(abs(i['x2']-i['x']),.01) if line else i['w']
            h=max(abs(i['y2']-i['y']),.01) if line else i['h']
            for n,v in dict(PinX=(x+w/2)/96,PinY=(self.height-y-h/2)/96,Width=w/96,Height=h/96,
                            LocPinX=w/192,LocPinY=h/192,Angle=0,FillPattern=1 if i['kind']=='rect' else 0,
                            FillForegnd=i['color'],LinePattern=1 if line else 0,LineColor=i['color'],
                            LineWeight=i.get('width',1)/96,ShdwPattern=0,VerticalAlign=1,
                            LeftMargin=0,RightMargin=0,TopMargin=0,BottomMargin=0).items():cell(s,n,v)
            cell(s,'LayerMember',0 if i['kind']=='text' else 1 if i.get('data') else 2)
            if i['kind']=='text':
                section=E.SubElement(s,f'{{{V}}}Section',N='Character')
                row=E.SubElement(section,f'{{{V}}}Row',IX='0')
                for n,v in dict(Font=3,Size=i['size']/96,Color=i['color'],Style=1 if i['bold'] else 0).items():cell(row,n,v)
                section=E.SubElement(s,f'{{{V}}}Section',N='Paragraph')
                row=E.SubElement(section,f'{{{V}}}Row',IX='0');cell(row,'HorzAlign',{'left':0,'center':1,'right':2}[i['align']])
                E.SubElement(s,f'{{{V}}}Text').text=i['text']
            else:
                geo=E.SubElement(s,f'{{{V}}}Section',N='Geometry',IX='0')
                if line:
                    coords=[((i['x']-x)/96,(y+h-i['y'])/96),((i['x2']-x)/96,(y+h-i['y2'])/96)]
                    cell(geo,'NoFill',1)
                else:coords=[(0,0),(w/96,0),(w/96,h/96),(0,h/96),(0,0)]
                for j,(a,b) in enumerate(coords):
                    row=E.SubElement(geo,f'{{{V}}}Row',T='MoveTo' if j==0 else 'LineTo',IX=str(j+1))
                    cell(row,'X',a);cell(row,'Y',b)
            if i.get('data'):
                section=E.SubElement(s,f'{{{V}}}Section',N='Property')
                row=E.SubElement(section,f'{{{V}}}Row',N='SourceData')
                cell(row,'Label','Source data');cell(row,'Type',0)
                cell(row,'Value',json.dumps(i['data'],sort_keys=True))
        return E.tostring(root,encoding='utf-8',xml_declaration=True)


def figures():
    ab=read('results/v8_eval_prep/batching_projection.csv')
    low=[r for r in ab if r['hardware_id']=='LPDDR5_c8_c4_s64_p512']
    high=[r for r in ab if r['hardware_id']=='HBM2_c32_c4_s64_p512']
    p=Page('E1_Batching','Cross-chunk batching: traffic reduction and latency-refresh tradeoffs')
    p.text(55,68,270,'(a) LPDDR5: traffic / request',17,bold=True)
    xy=p.axes(75,140,245,225,5,12,[],[0,4,8,12],'Pipeline organization','DRAM traffic (GB/request)')
    for j,r in enumerate(low):
        vlm,dit=float(r['VLM_GB_per_req']),float(r['DiT_GB_per_req'])
        x,_=xy(j+.5,0); _,yv=xy(0,vlm);_,yt=xy(0,vlm+dit)
        p.rect(x-16,yv,32,365-yv,GRAY,data=r)
        p.rect(x-16,yt,32,yv-yt,BLUE,data=r)
        p.text(x-25,yt-22,50,f'{vlm+dit:.2f}',12)
        p.text(x-25,371,50,('1','2 on','3 on','2 off','3 off')[j],12)
    p.rect(95,92,12,10,GRAY);p.text(110,86,48,'VLM',13,align='left')
    p.rect(175,92,12,10,BLUE);p.text(190,86,48,'DiT',13,align='left')
    for x,rows,title,xmax,ymax in [(415,low,'(b) LPDDR5: 102.4 GB/s',400,150),(765,high,'(c) HBM2: 1024 GB/s',200,100)]:
        p.text(x-10,68,280,title,17,bold=True)
        xy=p.axes(x,140,260,225,xmax,ymax,[0,xmax/2,xmax],[0,ymax/2,ymax],'Latency L (ms)','Refresh interval S (ms)')
        for batching,col in [('True',BLUE),('False',RED)]:
            seq=sorted([r for r in rows if r['batching']==batching],key=lambda r:int(r['k']))
            prev=None
            for r in seq:
                a,b=xy(float(r['L_ms']),float(r['S_ms']))
                if prev:p.line(*prev,a,b,col,1.8)
                p.dot(a,b,col,data=r);p.text(a-22,b-(27 if batching=='True' else -5),45,'k='+r['k'],12,color=col)
                prev=a,b
    p.text(385,89,300,'Blue: batched (k=1 is control)',13,color=BLUE)
    p.text(735,89,300,'Red: unbatched',13,color=RED)
    p.text(22,432,1036,'Fixed hardware and VLM/DiT allocation per panel. Model timing; no task-success measurement.',13,align='left')

    comparisons=read('results/v9_no_batching_domain/box_comparisons.csv')
    fronts=read('results/v9_no_batching_domain/frontier_points.csv')
    q=Page('E2_Hardware_DSE','Hardware DSE: resource frontiers and no-batching selection ablation',560)
    q.text(20,65,330,'(a) Full vs. no batching: 22 boxes',17,bold=True)
    colors={'identical':'#e6e6e6','task_strictly_better':'#aec7d2','task_extends':'#e9d6d3'}
    selected=[r for r in comparisons if r['eligibility']=='all_v7_eligible' and r['dimensions']=='cores_BW' and r['baseline']=='no_batching' and r['alternative']=='full']
    for r in selected:
        x=83+[100,150,200,250,300].index(int(r['Lmax_ms']))*48
        y=133+[200,150,100,75,50].index(int(r['Smax_ms']))*39
        pempty=int(r['baseline_vectors'])==0 and int(r['alternative_vectors'])==0
        q.rect(x,y,44,35,colors[r['relation']],data=r)
        q.text(x,y+7,44,'empty' if pempty else {'identical':'=','task_strictly_better':'better','task_extends':'extend'}[r['relation']],10)
    for j,t in enumerate([100,150,200,250,300]):q.text(83+j*48,337,44,str(t),12)
    for j,t in enumerate([200,150,100,75,50]):q.text(30,140+j*39,40,str(t),12)
    q.text(80,364,245,'Latency bound Lmax (ms)',14)
    q.text(30,101,290,'Rows: refresh bound Smax (ms)',13)
    for x,box,title in [(410,(200,50),'(b) Strict improvement: (200, 50)'),(765,(200,100),'(c) Extension: (200, 100)')]:
        q.text(x-36,65,340,title,16,bold=True)
        xy=q.axes(x,140,260,195,16,1050,[0,4,8,12,16],[0,256,512,1024],'Core count','Peak bandwidth (GB/s)')
        for arm,col in [('serial',GRAY),('no_batching',RED),('full',BLUE)]:
            records=[r for r in fronts if r['eligibility']=='all_v7_eligible' and r['dimensions']=='cores_BW' and r['arm']==arm and (int(r['Lmax_ms']),int(r['Smax_ms']))==box]
            coords=sorted({(int(r['n_cores']),float(r['BW_peak_GBps'])) for r in records})
            for a,b in zip(coords,coords[1:]):q.line(*xy(*a),*xy(*b),col,1.2 if arm=='no_batching' else 2.8)
            for a,b in coords:q.dot(*xy(a,b),col,3 if arm=='no_batching' else 5,data=dict(arm=arm,cores=a,BW=b))
    q.text(20,405,1040,'Gray: serial   |   Red: joint without batching (overlaps serial)   |   Blue: full RoboDSE',15)
    q.text(20,435,1040,'Fresh unpruned search: full vs. no batching = 5 better / 3 extended / 14 same; no batching vs. serial = 22 same.',14)
    q.text(20,464,1040,'Timing-box feasibility, not matched SR. 2D resource fronts; SRAM sensitivity reported separately.',13)
    case_path=ROOT/'results/v9_no_batching_domain/summary.json'
    if case_path.exists():
        case=json.loads(case_path.read_text())
        SOURCES.append(dict(path=str(case_path.relative_to(ROOT)),sha256=hashlib.sha256(case_path.read_bytes()).hexdigest()))
        q.text(20,500,1040,f'{case["hardware_identities"]} hardware identities; {case["configurations"]:,} configurations; {case["candidates"]:,} accepted candidates; all legal core splits.',14,bold=True)
        q.text(20,525,1040,f'{case["frontier_identity_checks"]} frontier identities / {case["unique_checks960"]} unique 960-request checks passed. Finite search domain; not independent trials.',13)

    sys.path.insert(0,str(ROOT/'vlasim'))
    from analysis.task_report import TaskGrid
    gridpath=ROOT/'vlasim/data/libero_dynamic_L_S.csv'
    grid=TaskGrid(gridpath)
    gridrows=read('vlasim/data/libero_dynamic_L_S.csv')
    rpage=Page('E3_SR_Projection','Task-space interpretation: empirical-grid projection (not in-loop validation)',520)
    rpage.text(40,68,570,'(a) Task surface: main-case timing window',17,bold=True)
    xy=rpage.axes(80,135,520,260,500,250,[0,100,200,300,400,500],[0,50,100,150,200,250],'Latency L (ms)','Refresh interval S (ms)')
    # Every colored tile has an in-hull query; outside coverage remains white.
    for l in range(100,500,10):
        for s in range(50,250,10):
            value=grid.lookup(l+5,s+5)
            if value['valid_only'] is None or any(grid.lookup(a,b)['valid_only'] is None
                for a,b in [(l,s),(l+10,s),(l,s+10),(l+10,s+10)]):continue
            t=max(0,min(1,value['valid_only']/.55))
            color='#'+''.join(f'{round(a+(b-a)*t):02x}' for a,b in zip((246,243,235),(120,162,178)))
            a,b=xy(l,s+10);rpage.rect(a,b,10*520/500,10*260/250,color,
                data=dict(L_ms=l+5,S_ms=s+5,estimated_SR_pct=100*value['valid_only']))
    # TaskGrid exposes points through its stored input; parse the same explicit columns.
    for row in gridrows:
        l=float(row['L (ms)']);s=float(row['S (ms)'])
        if l>500 or s>250:continue
        rpage.dot(*xy(l,s),'#777777',2)
    prev=None
    for row in low[:3]:
        a,b=xy(float(row['L_ms']),float(row['S_ms']))
        if prev:rpage.line(*prev,a,b,RED,2)
        rpage.dot(a,b,RED,4,data=row);rpage.text(a+4,b-24,75,'k='+row['k'],14,color=RED)
        prev=a,b
    rpage.text(650,68,390,'(b) Same-hardware projected mean SR',17,bold=True)
    for j,row in enumerate(low[:3]):
        y=150+j*68;v=float(row['estimated_mean_SR_pct'])
        rpage.text(650,y,90,'k='+row['k'],17)
        rpage.rect(752,y+2,v*4,23,BLUE if j<2 else RED,data=row)
        rpage.text(950,y,95,f'{v:.2f}%',17)
    rpage.text(650,372,390,'17,992 / 39,928 candidates covered',15)
    for j in range(28):
        t=j/27
        color='#'+''.join(f'{round(a+(b-a)*t):02x}' for a,b in zip((246,243,235),(120,162,178)))
        rpage.rect(720+j*8,343,8,12,color)
    rpage.text(650,339,65,'SR (%)',13)
    rpage.text(715,355,30,'0',11);rpage.text(930,355,30,'55',11)
    rpage.text(650,400,390,'True serial baselines: no covered SR comparison',13)
    rpage.text(20,455,1040,'Colored field: piecewise-linear estimates within grid coverage. Gray points: aggregate observations.',13)
    rpage.text(20,480,1040,'Direct robotic rollouts are pending. No measured same-hardware SR gain is claimed.',14,bold=True)
    return [p,q,rpage]


def package(pages):
    E.register_namespace('',V);E.register_namespace('r',R)
    def xml(element, ns):
        E.register_namespace('', ns)
        return E.tostring(element, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(REFERENCE) as reference:
        document=reference.read('visio/document.xml')
        original_rels=E.fromstring(reference.read('visio/_rels/document.xml.rels'))
        docrels=E.Element(f'{{{P}}}Relationships')
        theme_paths=[]
        for rel in original_rels:
            if rel.get('Type').endswith('/theme'):
                docrels.append(rel);theme_paths.append('visio/'+rel.get('Target'))
        E.SubElement(docrels,f'{{{P}}}Relationship',Id='rIdEvalPages',Type='http://schemas.microsoft.com/visio/2010/relationships/pages',Target='pages/pages.xml')
        files={'visio/document.xml':document,'visio/_rels/document.xml.rels':xml(docrels,P)}
        for path in theme_paths:files[path]=reference.read(path)
        pagesxml=E.Element(f'{{{V}}}Pages');rels=E.Element(f'{{{P}}}Relationships')
        for i,page in enumerate(pages,1):
            p=E.SubElement(pagesxml,f'{{{V}}}Page',ID=str(i),Name=page.name,NameU=page.name,IsCustomName='1',IsCustomNameU='1')
            sheet=E.SubElement(p,f'{{{V}}}PageSheet',LineStyle='0',FillStyle='0',TextStyle='0')
            for n,v in dict(PageWidth=page.width/96,PageHeight=page.height/96,PageScale=1,DrawingScale=1,DrawingSizeType=0,DrawingScaleType=0).items():
                E.SubElement(sheet,f'{{{V}}}Cell',N=n,V=str(v))
            layers=E.SubElement(sheet,f'{{{V}}}Section',N='Layer')
            for ix,name in enumerate(('Labels','Data marks','Axes and guides')):
                row=E.SubElement(layers,f'{{{V}}}Row',IX=str(ix))
                for n,v in dict(Name=name,NameUniv=name,Visible=1,Print=1,Lock=0).items():
                    E.SubElement(row,f'{{{V}}}Cell',N=n,V=str(v))
            E.SubElement(p,f'{{{V}}}Rel',{f'{{{R}}}id':f'rId{i}'})
            E.SubElement(rels,f'{{{P}}}Relationship',Id=f'rId{i}',Type='http://schemas.microsoft.com/visio/2010/relationships/page',Target=f'page{i}.xml')
            E.register_namespace('',V)
            files[f'visio/pages/page{i}.xml']=page.xml()
        files['visio/pages/pages.xml']=xml(pagesxml,V)
        files['visio/pages/_rels/pages.xml.rels']=xml(rels,P)
        rootrels=E.Element(f'{{{P}}}Relationships')
        E.SubElement(rootrels,f'{{{P}}}Relationship',Id='rId1',Type='http://schemas.microsoft.com/visio/2010/relationships/document',Target='visio/document.xml')
        files['_rels/.rels']=xml(rootrels,P)
        types=E.Element(f'{{{C}}}Types')
        E.SubElement(types,f'{{{C}}}Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml')
        E.SubElement(types,f'{{{C}}}Default',Extension='xml',ContentType='application/xml')
        for path in files:
            if path.endswith('.rels'):continue
            mime=('application/vnd.ms-visio.drawing.main+xml' if path=='visio/document.xml' else
                  'application/vnd.ms-visio.pages+xml' if path.endswith('/pages.xml') else
                  'application/vnd.ms-visio.page+xml' if path.startswith('visio/pages/page') else
                  'application/vnd.openxmlformats-officedocument.theme+xml')
            E.SubElement(types,f'{{{C}}}Override',PartName='/'+path,ContentType=mime)
        files['[Content_Types].xml']=xml(types,C)
        with zipfile.ZipFile(OUT/'RoboDSE_Evaluation.vsdx','w',zipfile.ZIP_DEFLATED) as z:
            for path,data in files.items():z.writestr(path,data)
    for page in pages:(OUT/(page.name+'.svg')).write_text(page.svg())
    (OUT/'figure_manifest.json').write_text(json.dumps(dict(reference=str(REFERENCE),
        reference_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),sources=SOURCES,
        pages=[dict(name=p.name,editable_shapes=len(p.items)) for p in pages],
        semantics='Native Visio shapes, no embedded chart bitmap; source data on data-bearing shapes.'),indent=2)+'\n')


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    package(figures())
