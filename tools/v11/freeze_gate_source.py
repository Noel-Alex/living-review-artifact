"""Retain the exact core source identified by the completed gate's recorded hash.

The only intervening core change adds a reporting-only five-class metric.
Reconstruct that earlier source and require byte-for-byte hash identity before saving.
"""
from wpa_core import *

target = Path(__file__).parent/'frozen/wpa_core_gate.py'
expected = read(OUT/'reproduction-gate.json')['provenance']['input_sha256']['tools/v11/wpa_core.py']
if target.exists():
    assert sha(target)==expected
    print('Existing gate source snapshot matches recorded SHA-256.')
    raise SystemExit(0)
source = Path(__file__).with_name('wpa_core.py').read_text(encoding='utf-8')
source = source.replace("    predicted_five = predicted\n    if predicted == 'preserved' and at is not None and row.get('anchor_at') is not None:\n        predicted_five = 'moved file' if at[0] != row['anchor_at'][0] else ('in place' if at[1] == row['anchor_at'][1] else 'shifted')\n",'')
source = source.replace("                classification_accuracy=int(predicted == actual), classification_five_accuracy=int(predicted_five == row['cls']),\n                missed=int(changed and not request),", "                classification_accuracy=int(predicted == actual), missed=int(changed and not request),")
source = source.replace("'classification_accuracy', 'classification_five_accuracy', 'missed'", "'classification_accuracy', 'missed'")
expected = read(OUT/'reproduction-gate.json')['provenance']['input_sha256']['tools/v11/wpa_core.py']
actual = hashlib.sha256(source.encode('utf-8')).hexdigest()
assert actual == expected, (actual,expected)
target = Path(__file__).parent/'frozen/wpa_core_gate.py'
target.parent.mkdir(exist_ok=True)
target.write_bytes(source.encode('utf-8'))
assert sha(target)==expected
write('gate-source-snapshot.json',{'path':str(target.relative_to(ROOT)).replace('\\','/'), 'sha256':expected,
    'purpose':'Exact core used for matcher gate, preserved after a reporting-only metric extension; the reconstruction is accepted only because its bytes match the pre-existing recorded SHA-256.'})
print('Gate source snapshot matches recorded SHA-256.')
