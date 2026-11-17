"""Scientific figures from archived V6 tables, with nonblank and text-bounds checks."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from v6_common import ROOT,load,write_json,digest
from v51_package import read_csv


def save(fig,name):
    out=ROOT/'paper/figures';out.mkdir(exist_ok=True)
    fig.tight_layout();fig.canvas.draw()
    renderer=fig.canvas.get_renderer();w,h=fig.canvas.get_width_height()
    inactive=set()
    for ax in fig.axes:
        for axis in (ax.xaxis,ax.yaxis):
            lo,hi=sorted(axis.get_view_interval())
            for tick in [*axis.get_major_ticks(),*axis.get_minor_ticks()]:
                if not lo<=tick.get_loc()<=hi:
                    inactive.update((id(tick.label1),id(tick.label2)))
    outside=[]
    for text in fig.findobj(matplotlib.text.Text):
        if id(text) in inactive or not text.get_visible() or not text.get_text():continue
        box=text.get_window_extent(renderer)
        if box.x0<-2 or box.y0<-2 or box.x1>w+2 or box.y1>h+2:outside.append(text.get_text())
    if outside:raise RuntimeError('Figure text outside canvas '+str(outside))
    target=out/(name+'.png');fig.savefig(target,dpi=160);plt.close(fig)
    pixels=np.asarray(Image.open(target).convert('RGB'))
    if pixels.std()<2:raise RuntimeError('Blank figure '+name)
    return dict(path=str(target),sha256=digest(target),width=pixels.shape[1],height=pixels.shape[0],
        pixel_std=float(pixels.std()),text_bounds_pass=True,visual_human_QA=False)


def run():
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    records=[]
    tiers=load(ROOT/'repair_selection.json')['tiers'];fig,ax=plt.subplots(figsize=(8,4))
    names=list(tiers);bars=[tiers[k]['eta_seq'] for k in names]
    ax.bar(names,bars,color=['#287a75' if x>=.8 else '#b44747' for x in bars])
    ax.axhline(.8,color='#333333',linestyle='--',linewidth=1)
    ax.set(ylim=(0,1.04),ylabel='Sequential efficiency (three-grain median)',
        title='Selected native identities; GDDR6 conditional on NoRefresh')
    records.append(save(fig,'seq_gate'))
    front=read_csv(ROOT/'paper/frontier_by_memory.csv');fig,ax=plt.subplots(figsize=(9,5))
    colors={'LPDDR5':'#287a75','GDDR6':'#af5a3d','HBM2':'#665088'}
    styles=['-','--',':','-.']
    for index,memory in enumerate(sorted({r['memory'] for r in front})):
        points=sorted([r for r in front if r['memory']==memory],key=lambda r:float(r['S_s']))
        x=np.array([float(r['S_s'])*1000 for r in points]);y=np.array([float(r['L_s'])*1000 for r in points])
        mask=(x<=300)&(y<=600)
        ax.plot(x[mask],y[mask],label=memory,color=colors[memory.split('_')[0]],linestyle=styles[index%4],linewidth=1.5)
    ax.set(xlabel='Completion interval S (ms)',ylabel='Latency L (ms)',
        title='Retained primary-model frontiers (absolute DRAM timing unvalidated)')
    ax.legend(ncol=3,fontsize=8);ax.grid(alpha=.15)
    records.append(save(fig,'frontier_by_memory'))
    controls=read_csv(ROOT/'paper/k_ablation_summary.csv');fig,axes=plt.subplots(1,2,figsize=(10,4))
    for cores in (4,8):
        rows=sorted([r for r in controls if r['memory']=='LPDDR5_c8' and int(r['n_cores'])==cores and r['dit_batching']=='True'],
            key=lambda r:int(r['dit_stages']))
        axes[0].plot([int(r['dit_stages']) for r in rows],[float(r['steady_dit_GB_per_req']) for r in rows],
            marker='o',label=f'{cores} cores')
        axes[1].plot([int(r['dit_stages']) for r in rows],[float(r['Tmin_s'])*1000 for r in rows],
            marker='o',label=f'{cores} cores')
    axes[0].set(xlabel='Batching k',ylabel='DiT DRAM GB/request',xticks=[1,2,3])
    axes[1].set(xlabel='Batching k',ylabel='Minimum stable period (ms)',xticks=[1,2,3])
    for ax in axes:ax.legend();ax.grid(alpha=.15)
    fig.suptitle('LPDDR5 102.4 GB/s, same allocation within each hardware')
    records.append(save(fig,'k_ablation_lpddr5'))
    write_json(ROOT/'paper/figures/qa.json',dict(figures=records,
        scope='Programmatic nonblank pixel and text-canvas bounds checks only; no visual screenshot inspection available.'))


if __name__=='__main__':run()
