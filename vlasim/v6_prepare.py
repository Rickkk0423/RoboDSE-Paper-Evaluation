"""Freeze V6 native diagnostic inputs without reusing heldout data."""
import shutil

from v6_common import ROOT,OLD,load,digest,write_json


def prepare():
    out=ROOT/'seq_input'
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Preserve frozen input '+str(out))
    out.mkdir(parents=True,exist_ok=True)
    original=load(OLD/'stage1_input/manifest.json');items=[]
    for previous in original['items']:
        config=previous['config']
        if config['id'] not in ('GDDR6_c16','GDDR6_c24','GDDR6_c36','HBM2_c32'):
            continue
        seq=original['seq_traces']
        for task in seq:
            shutil.copy2(OLD/'stage1_input'/task['path'],out/task['path'])
        refreshes=('NoRefresh','PerBank','AllBank') if config['standard']=='GDDR6' else (config['refresh'],)
        for refresh in refreshes:
            for mapper in ('MOP4CLXOR','ChRaBaRoCo','RoBaRaCoCh','RITAddrMapper'):
                for mode in ('aggregate','independent'):
                    for outstanding in ((512,8192) if mapper=='MOP4CLXOR' else (512,)):
                        name=f'{config["id"]}_{refresh}_{mapper}_{mode}_q{outstanding}'
                        tasks=[dict(t,id=f'seq_{i}') for i,t in enumerate(seq)]
                        items.append(dict(id=name,config=dict(config,refresh=refresh),mapper=mapper,mode=mode,
                            outstanding=outstanding,tasks=tasks))
    write_json(out/'manifest.json',dict(items=items,source_sha256=digest(__file__),
        previous_manifest_sha256=digest(OLD/'stage1_input/manifest.json'),
        unsupported_mappers=dict(PassThroughAddrMapper='Requires predecoded addr_vec; raw-address frontend supplies none. '
            'Not a physical raw-address mapping; not executed.'),
        refresh_scope='GenericDDR has a required refresh_manager child, no implicit default. '
            'Compare explicit NoRefresh, PerBank and AllBank instead of inventing a default.',
        scope='All 3 original seq granularities. 512 vs 8192 in-flight is an explicit frontend diagnostic. '
            'No heldout used. Nonpower aggregate constructor is attempted and failure archived.'))
    print('Frozen seq variants',len(items),flush=True)


if __name__=='__main__':
    prepare()
