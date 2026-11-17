"""V6 isolated outputs and shared evidence helpers."""
import json
from pathlib import Path

from v5_protocol import digest,write_json
from case_v3_main import write_csv

ROOT=Path('results/v6')
OLD=Path('results/v5_1')


def load(path):
    return json.loads(Path(path).read_text())


def frozen(directory,manifest):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'manifest.json',manifest)


def preserve():
    manifest=load(OLD/'delivery_manifest.json')
    changed=[]
    for name,sha in manifest['artifacts_sha256'].items():
        path=OLD/name
        if not path.is_file() or digest(path)!=sha:
            changed.append(str(path))
    for name,sha in manifest['sources_sha256'].items():
        if not Path(name).is_file() or digest(name)!=sha:
            changed.append(name)
    if changed:
        raise RuntimeError('Prior V5.1 delivery changed '+str(changed))
    return dict(passed=True,artifacts=len(manifest['artifacts_sha256']),
        sources=len(manifest['sources_sha256']),manifest_sha256=digest(OLD/'delivery_manifest.json'))
