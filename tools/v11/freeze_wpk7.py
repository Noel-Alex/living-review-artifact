"""Record the WP K7 freeze (protocol, code, units) before any locator outcome is read."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ('review/V12-PROTOCOL-K7.md', 'tools/v12/rab_cases.py', 'tools/v12/rab_fetch.py', 'tools/v11/run_wpk7.py',
         'tools/v11/analyze_wpk7.py', 'tools/v11/analyze_wpk6.py', 'tools/v11/wpi_core.py', 'tools/v11/wpb_variants.py',
         'tools/v11/wpc_adapters.py', 'evidence/v12-wpk7/units.json', 'evidence/v12-wpk7/fetch-report.json',
         'evidence/v12-wpk7/download/rab-1.1.0.zip')
out = ROOT / 'evidence/v12-wpk7/protocol-freeze.json'
assert not out.exists(), 'already frozen; changes need a numbered amendment'
rec = dict(recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), python=sys.version,
           note='Frozen before any K7 locator outcome. The 12-case smoke run checked execution only and was not read.',
           sha256={f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in FILES})
out.write_text(json.dumps(rec, indent=1) + '\n', encoding='utf-8')
print(json.dumps(rec, indent=1))
