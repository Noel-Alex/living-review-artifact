"""Keep the superseded reporting diagnostic before regenerating final summaries."""
from wpa_core import *
folder = OUT/'diagnostic-initial-analysis'
folder.mkdir(exist_ok=True)
files = ['safety-metrics.json','error-analysis.json','numerical-audit.json','effort-dominance.json',
         'cluster-uncertainty.json','factorial-summary.json','calibration.json']
saved = []
for name in files:
    path = OUT/name
    if path.exists() and not (folder/name).exists():
        (folder/name).write_bytes(path.read_bytes())
        saved.append(name)
write('reporting-correction.json',{'superseded_files':saved,'reason':
    'A reporting-only five-class classification extension initially treated compact grid wrong-placement sentinels as real coordinates. The compact grid supports three-state classification, safety and correctness, but not movement-subclass accuracy for incorrect placements. Final summaries mark that optional coordinate-dependent grid metric unavailable instead. Native method outputs retain real coordinates and support the five-class metric. Existing primary three-state, placement, safety, bootstrap, factorial and selection results are unchanged. Diagnostic outputs are retained, not used in the handoff.',
    'matcher_changed':False,'gate_core_snapshot':'tools/v11/frozen/wpa_core_gate.py'})
print('Preserved initial reporting diagnostic.')
