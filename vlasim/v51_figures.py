"""Render finite-window model frontiers and paired k controls without cost ranking."""
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from v51_package import read_csv
from v51_workflow import ROOT


def render():
    out=ROOT/'figures';out.mkdir(exist_ok=True)
    rows=[r for r in read_csv(ROOT/'attainable.csv') if r['model']=='v51' and
        r['track']=='neusim_unsliced' and r['bw_policy']=='fair' and r['scenario']=='main' and
        r['sram_mb']=='64' and r['local_kb']=='512']
    memories=sorted({r['memory'] for r in rows},key=lambda s:({'LPDDR5':0,'GDDR6':1,'HBM2':2}[s.split('_')[0]],int(s.split('c')[-1])))
    fig,axes=plt.subplots(2,5,figsize=(18,7),layout='constrained')
    palette={1:'#8a8a8a',2:'#16697a',3:'#489b8b',4:'#a6a642',6:'#d7a447',8:'#c96b52',12:'#ae4b80',16:'#6c548b'}
    for ax,memory in zip(axes.flat,memories):
        for cores,color in palette.items():
            points=[r for r in rows if r['memory']==memory and int(r['n_cores'])==cores]
            points.sort(key=lambda r:float(r['S_s']))
            ax.plot([float(r['S_s'])*1000 for r in points],[float(r['L_s'])*1000 for r in points],
                '.-',label=f'{cores} cores',color=color,linewidth=.8,markersize=3)
        ax.set_title(memory,fontsize=10);ax.set_xlabel('S (ms)');ax.set_ylabel('L (ms)')
        ax.grid(alpha=.18)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside lower center',ncol=8,fontsize=9)
    fig.suptitle('V5.1 model frontiers: DRAM unvalidated, trend-only | 64MB shared, 512KB private',fontsize=12)
    fig.savefig(out/'frontiers.png',dpi=150);plt.close(fig)
    controls=[r for r in read_csv(ROOT/'k_ablation.csv') if r['model']=='v51' and r['bg']=='False' and
        r['sram_mb']=='64' and r['local_kb']=='512' and r['n_cores']=='8' and r.get('Tmin_s') and r['dit_batching']=='True']
    fig,axes=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
    for memory in memories:
        points=sorted([r for r in controls if r['memory']==memory],key=lambda r:int(r['dit_stages']))
        if not points:
            continue
        for ax,key,scale in zip(axes,('Tmin_s','steady_dit_GB_per_req','steady_dit_busy'),(1000,1,100)):
            ax.plot([int(r['dit_stages']) for r in points],[float(r[key])*scale for r in points],'.-',label=memory)
    for ax,label in zip(axes,('Tmin (ms)','Steady DiT traffic (GB/request)','Steady DiT busy (%)')):
        ax.set_xlabel('k');ax.set_xticks([1,2,3]);ax.set_ylabel(label);ax.grid(alpha=.18)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=5,fontsize=8)
    fig.suptitle('Same-split k controls per memory | 8 cores, 64MB shared | trend-only',fontsize=11)
    fig.savefig(out/'k_controls.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    render()
