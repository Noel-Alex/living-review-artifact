"""Append a separately hashed amendment, preserving every original protocol byte."""
import sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *

AMENDMENT='''

<!-- WP-C6-AMENDMENT-START -->
## C6 amendment: matcher-independent safety and within-file hybrid

This amendment is registered after C1–C5 completed and after their results were inspected. All C6 analyses are therefore retrospective/exploratory, including CodeMapper data; they are not a new held-out evaluation. The exact preceding C1–C5 byte segment remains immutable at SHA-256 b5af90afd37561f29c76ad87a7585d33e31adfe7d89ad7de57bd8ce3e639d2ac. `c6-protocol-freeze.json` records its byte length/hash, the amendment-only hash, the combined-file hash and the UTC freeze time before any C6 evaluation. Its C1–C5 completion pointer must pass. No earlier freeze record is modified.

### Fixed methods and safety transfer

Evaluate GumTree, native-readonly CodeMapper, the contextual tracker strictly within the original path, and a hybrid using that tracker followed only on completed no-match by deployed cascade tier 4 (cross-file exact). A tracker execution error remains an error, not an opportunity to fall back. If the source path is absent in the new map, strict same-path tracking returns completed no-match. A saved rename-adjusted tracker output is reused only when its returned path is the original path; other required tracker calls use the same pinned executable. The hybrid may use only the saved deployed cross-exact result, or the identical pinned cross-file tier when no saved deployed result is available. It cannot use an oracle target, another cascade tier or a lower threshold.

Locations and native ranges are not reranked by the safety layer. Four fixed layer versions are reported for each matcher: quotation only, +IG, +AG, +IG+AG. Normalize a window as the tuple of stripped nonempty lines, exactly as B1. The source quotation is the full occupied old anchor lines. A mapper with native line range uses that complete returned range; line-only tracker uses original height clipped at EOF, explicitly marked as a safety-window projection rather than native range recovery. CodeMapper's character boundaries remain separately retained; C6 tests its line-expanded workflow window and never trims a prediction to annotation columns.

For a completed location, equal normalized quotation/window means exact/content-match at the old path/start, otherwise moved/content-match; unequal means changed. Completed no location means removed. Failures remain execution_error and inspection-required. Baseline changed/removed and all errors request re-check.

Apply the frozen B1 post-selection guard predicates verbatim, without changing frozen files. For a normalized-equal location, AG computes expected_start from the same pinned diff function on the original path, and counts old/new copies in the returned file using frozen runs. If candidate differs from original path or zero-based start differs from expected, and old candidate text exists and new_count <= old_count, retain moved and request re-check with pre-existing-copy. No unavailable old file is replaced with a fabricated zero. IG uses the frozen profile: Python .py/.pyw compares base and relative indentation, other languages relative indentation only; a mismatch changes the label to changed and requests re-check. AG is applied before IG as frozen. These guards do not relocate the underlying matcher; B1's candidate-selection preference cannot be applied to an already fixed location and is explicitly outside this transfer. No VW change or threshold tuning is introduced.

### Populations and execution

Regenerate all seed-2 (20261027) B1 indentation, duplication and short/repeated-quotation suites using the unchanged frozen generators, plus the original seed-2 controlled benchmark. Verify metadata/input hashes and saved deployed/variant identities against B1 before new outcomes are used. Reuse complete C1–C5 raw GumTree/CodeMapper mappings for original controlled seed 2, all 15,064 real histories and all 2,392 external cases; obtain the same native tools on the additional stress pairs. Synthetic CodeMapper inputs are isolated two-commit bare fixture repositories containing original files and the modified map; never execute fixture source. Matching keeps C1–C5 timeouts, tool pins, native resolver, failure semantics and isolated Python -I -B. Verify all frozen B1 hashes before each batch and each safety-family call. Preserve every error and interrupted attempt; resume only missing IDs. No missing-object repair may change pinned inputs or algorithms.

### Outcomes and fixed interpretation

Report the complete WP A metric family, Wilson intervals, label confusion, explicit re-check policy and raw failure counts by suite/operator, real sampling group/project, external dataset and actual language. Report human A/B non-Python separately from Java-derived records. Layer-only variants must preserve placement/range and character-mapping scores exactly. Keep lost among survivors, missed among edited/gone and wrong-silent among all targets. The hybrid is allowed to alter placement only by the registered cross-exact fallback.

Compare each combination with deployed and the frozen combined .85/.55 variants, reporting paired discordances and exact conditional binomial tests; use 10,000 seed-20261031 cluster bootstraps (source file for constructed trials, commit pair for histories, repository+commit pair for external cases) for headline accuracy, missed, wrong-silent, lost and false re-check contrasts. Nominal exploratory inference, no multiplicity-adjusted superiority claim. Define descriptive safety dominance in advance as no higher missed or wrong-silent rate, at least one strictly lower, and lost-rate increase <= 1 percentage point; separately mark inferential support only if both safety difference upper confidence limits are <=0. Always expose false re-check cost, placement and errors; descriptive dominance is not a certificate of semantic identity or workload benefit.

C1–C5 findings, protocol segment and artifacts remain a separate completed package. C6 outputs live under `evidence/v11-wpc/c6/`, generated TeX under its `tex/`, and `review/V11-WPC-C6-RESULTS.md`. Report limits and adverse outcomes. No app/AGENTS/earlier evidence edits, project commits/pushes, external messages, agents or new conversations.
'''

def main():
    verify_freeze();assert read(OUT/'c15-completion.json')['data']['complete']
    path=ROOT/'review/V11-PROTOCOL-C.md';original=path.read_bytes();assert sha(path)=='b5af90afd37561f29c76ad87a7585d33e31adfe7d89ad7de57bd8ce3e639d2ac'
    amendment=AMENDMENT.encode('utf-8')
    (OUT/'protocol-c15-original-bytes.md').open('xb').write(original)
    with path.open('ab') as f:f.write(amendment)
    assert path.read_bytes()[:len(original)]==original
    write('c6-protocol-freeze.json',dict(timestamp_utc=now(),original_bytes=len(original),original_sha256=hashlib.sha256(original).hexdigest(),amendment_sha256=hashlib.sha256(amendment).hexdigest(),combined_sha256=sha(path),c15_complete_sha256=sha(OUT/'c15-completion.json'),statement='No C6 evaluation has run before this timestamp; C1-C5 already complete.'))
    print('C6 amendment frozen',hashlib.sha256(amendment).hexdigest(),now())
if __name__=='__main__':main()
