"""Archive primary sources; unavailable vendor claims remain explicitly attributed."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import urllib.request

from v7_common import ROOT, write_json, digest, load


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden and value.strip():
            self.parts.append(value.strip())


def fetch():
    out = ROOT / 'cost/sources'
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'manifest.json').exists():
        attempt = len(list(out.glob('acquisition_attempt_*.json')))
        write_json(out / f'acquisition_attempt_{attempt}.json', load(out / 'manifest.json'))
    sources = [
        ('lpddr_phy', 'https://arxiv.org/pdf/2503.11654', 'pdf'),
        ('spartus', 'https://arxiv.org/pdf/2108.02297', 'pdf'),
        ('rambus', 'https://www.rambus.com/blogs/memory-systems-for-ai-part-6/', 'html'),
        ('micron_lpcamm2', 'https://www.micron.com/products/memory/dram-modules/lpcamm2', 'html'),
        ('micron_hbm2e', 'https://www.micron.com/products/memory/hbm/hbm2e', 'html'),
    ]
    records = []
    for name, url, extension in sources:
        path = out / (name + '.' + extension)
        try:
            if not path.exists():
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read()
                    if extension == 'pdf' and not data.startswith(b'%PDF'):
                        raise ValueError('Not a PDF')
                    path.write_bytes(data)
            text = path.with_suffix('.txt')
            if extension == 'pdf':
                subprocess.run(['pdftotext', '-layout', str(path), str(text)], check=True)
            else:
                parser = Text()
                parser.feed(path.read_text())
                text.write_text('\n'.join(parser.parts) + '\n')
                write_json(path.with_suffix('.links.json'), parser.links)
            records.append(dict(id=name, url=url, path=str(path), sha256=digest(path),
                                extracted_text=str(text), status='retrieved_primary_source'))
        except Exception as exc:
            records.append(dict(id=name, url=url, status='access_or_extraction_failure', error=str(exc)))
    write_json(out / 'manifest.json', dict(sources=records,
        attribution='Only primary author/vendor sources; successful retrieval does not imply all claimed numbers verified.'))
    print('Primary source acquisition', [(r['id'], r['status']) for r in records], flush=True)


def numerical_verification():
    out = ROOT / 'cost/sources'
    lp = (out / 'lpddr_phy.txt').read_text()
    rb = (out / 'rambus.txt').read_text()
    sp = (out / 'spartus.txt').read_text()
    if not all(x in lp for x in ('2.89', '0.135', 'bump pads', 'x32')):
        raise RuntimeError('LPDDR PHY source does not support requested conversion')
    if not all(x in rb for x in ('1.5', '1.75', '256GB/s')):
        raise RuntimeError('Rambus source does not support equal-bandwidth ratio')
    if not all(x in sp for x in ('TABLE VII', '5.5 [43]', 'GDDR6')):
        raise RuntimeError('Spartus cross-check absent')
    write_json(out / 'numerical_verification.json', {
        'A_phy_LPDDR5': dict(status='verified_primary_numeric_inputs_proxy_not_validated',
            evidence=str(out / 'lpddr_phy.pdf'), sha256=digest(out / 'lpddr_phy.pdf'),
            location='page2 Section3; page1 x32 architecture',
            limitation='12nm LPDDR4X bump-limited area used as LPDDR5 proxy; no LPDDR5 silicon validation'),
        'A_phy_GDDR6': dict(status='verified_vendor_ratio_derived_from_V6_HBM2_estimate',
            evidence=str(out / 'rambus.html'), sha256=digest(out / 'rambus.html'),
            location='Memory Systems for AI Part6, equal256GB/s PHY comparison'),
        'e_dram_LPDDR5': dict(status='user_supplied_vendor_claim_not_independently_retrieved',
            evidence=str(ROOT / 'NEXT_STEPS_V7.md'), sha256=digest(ROOT / 'NEXT_STEPS_V7.md'),
            limitation='Micron technical brief not obtained; value supplied by author, device/module scope unspecified'),
        'e_dram_GDDR6': dict(status='user_supplied_vendor_center_with_verified_academic_crosscheck',
            vendor_center_independently_verified=False, evidence=str(ROOT / 'NEXT_STEPS_V7.md'),
            crosscheck_evidence=str(out / 'spartus.pdf'), crosscheck_sha256=digest(out / 'spartus.pdf'),
            crosscheck_pJ_per_bit=5.5, location='Spartus TableVII; this does not verify Micron7.5/6.0 center pair')})


if __name__ == '__main__':
    fetch()
    numerical_verification()
