"""Upload completed release parts with resumable asset checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Rickkk0423/RoboDSE-Paper-Evaluation'
TAG = 'v7-full-evidence'
OUT = ROOT / 'publication/release_assets'


def view():
    return json.loads(subprocess.check_output(['gh', 'release', 'view', TAG,
        '--repo', REPO, '--json', 'assets,url,isDraft']))


def main():
    uploaded = {r['name']: r['size'] for r in view()['assets']}
    while True:
        manifest_path = OUT / 'FULL_EVIDENCE_MANIFEST.json'
        parts = sorted(OUT.glob('full-evidence.tar.gz.part*'))
        ready = parts if manifest_path.exists() else parts[:-1]
        for path in ready:
            if uploaded.get(path.name) == path.stat().st_size:
                continue
            for attempt in range(3):
                result = subprocess.run(['gh', 'release', 'upload', TAG, str(path),
                    '--repo', REPO, '--clobber'])
                if result.returncode == 0:
                    break
                time.sleep(5)
            else:
                raise RuntimeError('Upload failed: ' + path.name)
            uploaded[path.name] = path.stat().st_size
            print('Uploaded', path.name, flush=True)
        if manifest_path.exists():
            break
        time.sleep(5)
    manifest = json.loads(manifest_path.read_text())
    for name in ('FULL_EVIDENCE_MANIFEST.json', 'SHA256SUMS'):
        subprocess.run(['gh', 'release', 'upload', TAG, str(OUT / name),
                        '--repo', REPO, '--clobber'], check=True)
    release = view()
    sizes = {r['name']: r['size'] for r in release['assets']}
    errors = [r['name'] for r in manifest['parts'] if sizes.get(r['name']) != r['bytes']]
    # The REST API supplies server-side digests on supported assets.
    api = json.loads(subprocess.check_output(['gh', 'api', 'repos/' + REPO + '/releases']))
    remote = next(r for r in api if r['tag_name'] == TAG)
    digests = {a['name']: a.get('digest') for a in remote['assets']}
    for part in manifest['parts']:
        if digests.get(part['name']) and digests[part['name']] != 'sha256:' + part['sha256']:
            errors.append(part['name'] + ':digest')
    result = dict(passed=not errors, repo=REPO, tag=TAG, parts=len(manifest['parts']),
                  bytes=sum(r['bytes'] for r in manifest['parts']), errors=errors,
                  server_digests_available=all(digests.get(r['name']) for r in manifest['parts']))
    (ROOT / 'publication/UPLOAD_VERIFICATION.json').write_text(json.dumps(result, indent=2) + '\n')
    if errors:
        raise RuntimeError(errors)
    subprocess.run(['gh', 'release', 'edit', TAG, '--repo', REPO, '--draft=false'], check=True)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
