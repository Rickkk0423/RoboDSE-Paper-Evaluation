"""Stream the complete project payload into checksummed 1 GiB release parts."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '__pycache__', '.pytest_cache', '.DS_Store', 'publication'}


class Parts:
    def __init__(self, out):
        self.out, self.stream, self.size, self.rows = out, None, 0, []

    def write(self, data):
        original = len(data)
        while data:
            if self.stream is None:
                path = self.out / ('full-evidence.tar.gz.part%03d' % len(self.rows))
                self.stream = path.open('xb')
                self.hash, self.size = hashlib.sha256(), 0
                self.rows.append({'name': path.name})
            chunk = data[:min(len(data), 1024 ** 3 - self.size)]
            self.stream.write(chunk)
            self.hash.update(chunk)
            self.size += len(chunk)
            data = data[len(chunk):]
            if self.size == 1024 ** 3:
                self.close_part()
        return original

    def close_part(self):
        if self.stream:
            self.stream.close()
            self.rows[-1].update(bytes=self.size, sha256=self.hash.hexdigest())
            print(self.rows[-1]['name'], self.size, flush=True)
            self.stream = None


def main():
    out = ROOT / 'publication/release_assets'
    out.mkdir(parents=True, exist_ok=False)
    parts = Parts(out)
    def filter_entry(info):
        return None if any(p in SKIP for p in Path(info.name).parts) else info
    with tarfile.open(fileobj=parts, mode='w|gz', compresslevel=1) as archive:
        for path in sorted(ROOT.iterdir()):
            if path.name not in SKIP:
                archive.add(path, arcname=path.name, filter=filter_entry)
    parts.close_part()
    result = dict(format='concatenated gzip tar stream', parts=parts.rows,
        exclusions=sorted(SKIP), frozen_results_included=True,
        restore='cat full-evidence.tar.gz.part* | tar -xzf - -C EMPTY_DIRECTORY')
    (out / 'FULL_EVIDENCE_MANIFEST.json').write_text(json.dumps(result, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(''.join(r['sha256'] + '  ' + r['name'] + '\n' for r in parts.rows))


if __name__ == '__main__':
    main()
