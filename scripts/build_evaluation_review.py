"""Compile the review PDF from independently rendered Visio pages."""
from pathlib import Path
import shutil
import subprocess
import json
import pymupdf as fitz

OUT=Path(__file__).resolve().parents[1]/'paper/evaluation_delivery'
BUILD=OUT/'build'
BUILD.mkdir(exist_ok=True)
for i in range(1,4):
    subprocess.run(['rsvg-convert','-f','pdf','-o',str(OUT/f'figure_{i}.pdf'),
                    str(OUT/f'visio_page_{i}.svg')],check=True)
for i in (1,2):
    run=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error',
                        '-output-directory=build','review.tex'],cwd=OUT,capture_output=True,text=True,errors='replace')
    (BUILD/f'pass{i}.log').write_text(run.stdout+run.stderr)
    run.check_returncode()
log=(BUILD/'review.log').read_text(errors='replace')
assert 'undefined references' not in log
assert 'Overfull' not in log
shutil.copyfile(BUILD/'review.pdf',OUT/'review.pdf')
subprocess.run(['pdftoppm','-scale-to','1400','-png',str(OUT/'review.pdf'),str(BUILD/'review-page')],check=True)
pages=[]
for p in fitz.open(OUT/'review.pdf'):
    w,h=p.rect.width,p.rect.height
    words=p.get_text('words')
    outside=[e[4] for e in words if e[0]<0 or e[1]<0 or e[2]>w or e[3]>h]
    assert not outside,outside
    pages.append(dict(words=len(words),out_of_page_words=outside))
(OUT/'pdf_validation.json').write_text(json.dumps(dict(pages=pages,overfull_boxes=False,
    undefined_references=False,rasterized=True,visual_inspection_completed=False),indent=2)+'\n')
print('Review compiled:',len(pages),'pages; no overfull boxes or unresolved references.')
