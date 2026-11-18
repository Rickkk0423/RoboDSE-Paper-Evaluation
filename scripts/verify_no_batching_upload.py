"""Verify published Release sizes and GitHub SHA-256 digests against local assets."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v9-no-batching-dse-20261118'
REPO = 'Rickkk0423/RoboDSE-Paper-Evaluation'


def run():
    release = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{REPO}/releases/tags/{TAG}']))
    assert not release['draft']
    assets = {a['name']: a for a in release['assets']}
    verified = []
    for name in ('no-batching-dse-evidence.tar.gz', 'SHA256SUMS', 'EVIDENCE_MANIFEST.json'):
        path = ROOT / 'publication/release_assets/v9_no_batching' / name
        with path.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        remote = assets[name]
        assert remote['state'] == 'uploaded'
        assert remote['size'] == path.stat().st_size
        if remote.get('digest'):
            assert remote['digest'] == f'sha256:{sha}'
            method = 'GitHub API SHA-256 digest'
        else:
            process = subprocess.Popen(['gh', 'api', f'repos/{REPO}/releases/assets/{remote["id"]}',
                '-H', 'Accept: application/octet-stream'], stdout=subprocess.PIPE)
            downloaded = hashlib.file_digest(process.stdout, 'sha256').hexdigest()
            assert process.wait() == 0 and downloaded == sha
            method = 'downloaded asset SHA-256'
        verified.append(dict(name=name, bytes=remote['size'], sha256=sha,
                             method=method, asset_id=remote['id'], url=remote['browser_download_url']))
    report = dict(verified_at_utc=datetime.now(timezone.utc).isoformat(), repository=REPO,
                  release_tag=TAG, release_url=release['html_url'], is_draft=release['draft'],
                  source_commit=release['target_commitish'], assets=verified, passed=True,
                  note='Remote bytes/digests verified; archive member hashes separately checked before upload.')
    (ROOT / 'publication/v9_no_batching/UPLOAD_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    run()
