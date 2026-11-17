"""Development-only fluid rule matching proportional saturated frontend issue shares."""
from collections import defaultdict
from dataclasses import dataclass,field

import numpy as np
from scipy.optimize import least_squares

from v6_common import ROOT,OLD,load,digest,write_json,write_csv
from v51_workflow import dev_samples,predicted
from vlasim import DRAMModel


@dataclass
class FrontendProportional(DRAMModel):
    issue_weights: dict=field(default_factory=dict)

    def allocate(self,peak,demands,policy='fair',targets=None):
        active={k:d for k,d in demands.items() if d>0}
        alloc={k:0. for k in demands};remaining=self.effective_bw(peak,len(active))
        while active and remaining>1e-9:
            total=sum(self.issue_weights.get(k,0.) for k in active)
            if total<=0:
                raise ValueError('Positive source issue weights required')
            shares={k:remaining*self.issue_weights.get(k,0.)/total for k in active}
            limited=[k for k in active if active[k]<=shares[k]]
            if not limited:
                alloc.update(shares);break
            for k in limited:
                alloc[k]=active.pop(k);remaining-=alloc[k]
        return alloc


def frontend_prediction(task,eta):
    counts=task['bytes_by_stream'];peak=task['peak_GBps']*1e9
    model=FrontendProportional(eta_seq=task['params']['eta_seq'],eta_mix=eta,
        issue_weights=dict(zip(('vlm','dit'),counts)))
    rates=model.allocate(peak,{k:float('inf') if b else 0. for k,b in zip(('vlm','dit'),counts)})
    return [b/rates[k]*1e9 if b else None for k,b in zip(('vlm','dit'),counts)]


def run():
    out=ROOT/'diagnosis';out.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    for sample in dev_samples():
        task=sample['task'];groups[task['standard']+('_bg' if task['bg'] else '_plain')].append(sample)
    fitted=load(OLD/'model_fit.json');metrics=[];summary=[];params={}
    for key,samples in sorted(groups.items()):
        def residual(x):
            values=[]
            for row in samples:
                estimates=frontend_prediction(row['task'],float(np.exp(x[0])))
                values.extend(a/b-1 for a,b in zip(row['result']['native']['last_completion_ns'],estimates) if b)
            return values
        fit=least_squares(residual,[np.log(.9)],bounds=([np.log(.05)],[np.log(2.)]))
        eta=float(np.exp(fit.x[0]));params[key]=eta
        for label,predict,efficiency in (('original_fair',predicted,fitted['groups'][key]['A_eta_mix']),
            ('frontend_proportional',frontend_prediction,eta)):
            errors=[]
            for row in samples:
                task=row['task'];estimates=predict(task,efficiency)
                for stream,(actual,estimate) in enumerate(zip(row['result']['native']['last_completion_ns'],estimates)):
                    if estimate is None:
                        continue
                    error=actual/estimate-1;errors.append(abs(error)*100)
                    metrics.append(dict(group=key,rule=label,id=task['id'],window=task['window'],
                        stream=('vlm','dit')[stream],actual_ns=actual,predicted_ns=estimate,
                        signed_error_pct=error*100,absolute_error_pct=abs(error)*100,eta_mix=efficiency))
            summary.append(dict(group=key,rule=label,flows=len(errors),mean_error_pct=float(np.mean(errors)),
                max_error_pct=max(errors),all_le_5pct=max(errors)<=5))
    candidate=all(r['all_le_5pct'] for r in summary if r['rule']=='frontend_proportional')
    write_csv(out/'development_metrics.csv',metrics);write_csv(out/'development_summary.csv',summary)
    write_json(out/'status.json',dict(status='development_only_not_validated',all_groups_le_5pct=candidate,
        eta_mix_by_standard_layout=params,source_development_sha256=digest(OLD/'development_input/manifest.json'),
        heldout_used_for_fit=False,source_sha256=digest(__file__),
        interpretation='Weights use entire finite replay trace byte counts, exactly matching offered() normalized-rank '
            'saturated merge in expectation, not FRFCFS completion fairness. Finite-window lookahead is not an online '
            'deployable scheduler. No native timing/locality claim, no DSE parameter replacement.',
        locality='Development W3/W4 are contiguous. W5 block sampling has no same-window full-address counterfactual '
            'in this development set; W5 locality versus arbitration cannot be causally separated from heldout '
            'residuals alone. Existing L1/L2 controls quantify sampling sensitivity, not an independent W5 model validation.'))
    if candidate:
        specs=[]
        for index,(memory,k,split,bg) in enumerate((('LPDDR5_c8',1,5,False),('LPDDR5_c16',2,6,True),
            ('LPDDR5_c32',3,6,False),('HBM2_c8',1,5,True),('HBM2_c16',2,6,False),
            ('HBM2_c32',3,7,True),('GDDR6_c16',1,4,False),('GDDR6_c24',2,6,True))):
            specs.append(dict(id=f'v7_draft_{index}',memory=memory,n_cores=10,sram_mb=48,local_kb=1024,
                mode='pipelined',vlm_cores=split,dit_stages=k,bg=bg,launches=['open','saturated'],
                windows=['W1','W3' if k==1 else 'W4','W5'],W2='N/A_pipeline',
                physical_identity='must use C accepted identity; excluded tiers require replacement before execution',
                window_rule='After 24 warmup requests, choose earliest continuous qualifying 0.5ms interval '
                    'starting strictly after 40% of measurement horizon; W5 complete-period selected protocol. '
                    'If unavailable, retain missing reason; never substitute another configuration.'))
        write_json(out/'next_heldout_spec_draft.json',dict(status='frozen_spec_draft_NOT_EXECUTED',items=specs,
            novel_hardware='10 cores / 48MB shared / 1024KB private, disjoint from all V3-V5.1 executed identities.',
            candidate_sha256=digest(out/'status.json'),requires_before_execution=['per_trace_hashes',
                'physical_native_identity_hashes','source_window_times','online_weight_definition_or_explicit_trace_lookahead_scope'],
            no_heldout_runs=True))
    print('Development candidate all <=5%:',candidate,summary,flush=True)


if __name__=='__main__':
    run()
