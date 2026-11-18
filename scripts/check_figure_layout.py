"""Check actual libvisio SVG text bounds using Chrome's font renderer."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]/'paper/evaluation_delivery'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1800,'height':1000})
    output=[]
    for i in range(1,4):
        page.goto((ROOT/f'visio_page_{i}.svg').as_uri())
        result=page.evaluate('''() => {
          const svg=document.documentElement;
          const v=svg.viewBox.baseVal;
          const texts=[...svg.querySelectorAll('text')].map(e=>{
            const b=e.getBBox();return {text:e.textContent.trim(),x:b.x,y:b.y,w:b.width,h:b.height};});
          const outside=texts.filter(b=>b.x<-.1 || b.y<-.1 || b.x+b.w>v.width+.1 || b.y+b.h>v.height+.1);
          const overlaps=[];
          for(let a=0;a<texts.length;a++)for(let b=a+1;b<texts.length;b++){
            const x=texts[a],y=texts[b];
            const w=Math.min(x.x+x.w,y.x+y.w)-Math.max(x.x,y.x);
            const h=Math.min(x.y+x.h,y.y+y.h)-Math.max(x.y,y.y);
            if(w>1&&h>1)overlaps.push([x.text,y.text]);
          }
          return {outside,overlaps,text_count:texts.length};
        }''')
        output.append(dict(page=i,**result))
    browser.close()
(ROOT/'layout_checks.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
