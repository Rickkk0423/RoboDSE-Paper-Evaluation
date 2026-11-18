"""Package complete new evidence without adding large raw files to Git history."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'publication/v9_no_batching'
ASSETS = ROOT / 'publication/release_assets/v9_no_batching'
FOLDERS = ['v8_no_batching', 'v8_no_batching_case_final', 'v9_no_batching_domain']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for folder in FOLDERS for p in (ROOT / 'results' / folder).rglob('*')
                   if p.is_file() and p.suffix != '.dylib')
    members = {str(p.relative_to(ROOT)): dict(bytes=p.stat().st_size, sha256=digest(p)) for p in paths}
    archive = ASSETS / 'no-batching-dse-evidence.tar.gz'
    with tarfile.open(archive, 'w:gz', compresslevel=6) as tar:
        for p in paths:
            tar.add(p, arcname=str(p.relative_to(ROOT)), recursive=False)
    checked = 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            expected = members[member.name]
            assert member.size == expected['bytes']
            assert hashlib.file_digest(tar.extractfile(member), 'sha256').hexdigest() == expected['sha256']
            checked += 1
    assert checked == len(members)
    info = dict(release_tag='v9-no-batching-dse-20261118', archive=archive.name,
                archive_bytes=archive.stat().st_size, archive_sha256=digest(archive),
                files=members, archive_readback_verified=checked,
                excluded='Rebuildable periodic.dylib only; all selected result data retained.')
    (OUT / 'EVIDENCE_MANIFEST.json').write_text(json.dumps(info, indent=2)+'\n')
    (ASSETS / 'SHA256SUMS').write_text(f'{info["archive_sha256"]}  {archive.name}\n')
    shutil.copyfile(OUT / 'EVIDENCE_MANIFEST.json', ASSETS / 'EVIDENCE_MANIFEST.json')
    shutil.copyfile(ASSETS / 'SHA256SUMS', OUT / 'SHA256SUMS')
    for folder in FOLDERS:
        shutil.copyfile(ROOT / 'results' / folder / 'summary.json', OUT / f'{folder}_summary.json')
    shutil.copyfile(ROOT / 'results/v9_no_batching_domain/independent_audit.json', OUT / 'independent_audit.json')
    print(json.dumps({k:v for k,v in info.items() if k!='files'},indent=2), flush=True)


if __name__ == '__main__':
    run()
