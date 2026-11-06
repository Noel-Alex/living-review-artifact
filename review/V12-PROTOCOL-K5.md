# V12 protocol K5: stratified, blinded adjudication of the syntax-tree reference

Answers professor review R02 item 7.1 and the critical deficiency "weak independent validation of AST-based ground truth". Frozen in `evidence/v12-wpk5/protocol-freeze.json` (protocol, code, sample, key and system prompt hashes) before any model call.

**The adjudicators are hosted language models, not human annotators.** Every output says so. A blinded human packet is prepared for the authors to decide on; it is not distributed.

## Sample (`tools/v11/wpk5_audit.py sample`, seed 20261108)

Pool: the WP I real-history rows (`evidence/v11-wpi/transfer`, suite `real`; 15,064) and the student-authored rows (`evidence/v11-wpi/students/rows.json`; 7,882). Strata, drawn in this order without replacement:

| Stratum | Definition | Eligible | Drawn |
|---|---|---|---|
| S-miss | every real-history target behind a deployed-cascade missed re-check | 37 | 37 |
| S-pair | changed targets decided by same-type pairing (`how = edited`) | 3,868 | 50 |
| S-del | targets the reference calls deleted, or relocated as a unique equal tree elsewhere | 749 | 50 |
| S-dis | the reference disagrees with at least two of CodeMapper, the contextual tracker and GumTree (+quote) on location or change status | 294 | 50 |
| S-aligned | aligned equal-tree controls | 18,329 | 50 |
| S-excl | candidates the reference excluded (WP A exclusion records, all reasons except `unparsable`) | 2,204 | 50 |

Students have no GumTree output, so for them S-dis needs both CodeMapper and the tracker to disagree.

## Blinded input

- OLD: the old file's lines from 40 above to 40 below the anchor, numbered, with the reviewed lines marked `>>`.
- NEW: the paired file in the new version (the git rename target if the path was renamed), numbered; the whole file up to 1,200 lines, otherwise a 1,200-line window centred on the old start line. The window is chosen without the reference. If the paired file no longer exists, the input says so.
- The adjudicator never sees the reference, the strata or any method's output. A reference location in another file therefore cannot be matched; such items are counted (`cross_file_reference`) and score as location disagreements.
- System prompt (frozen, verbatim in the freeze record) asks for JSON `{status: unchanged|edited|deleted, start, end, reason}`.

## Adjudicators

Beam (`reflection/beam-1.0-501b-a23b:free`, the WP J primary, via the local Hermes proxy) and Nemotron 3.5 Super (NVIDIA), with WP J's transport, settings (temperature 0), rate gate and retry rules. Refusals, transport failures and unparsable answers are recorded and counted as outcomes.

## Analysis

Per stratum and over all decided strata (everything but S-excl):

- status agreement with the reference (Wilson 95%) and Cohen's κ; the reference status is `edited` for `cls = edited`, `deleted` for `gone`, else `unchanged`;
- location agreement inside the paired file: exact start, start within ±2 lines, overlap with the reference span;
- model-model status agreement and κ;
- suspects: items on which both models disagree with the reference status (and the subset where they agree with each other). For S-miss, whether each suspect would lower the missed count if the models were right (both say `unchanged`), the direction the reference-error bound predicts;
- an implied upper bound on reference status error per stratum, **assuming** a two-model consensus against the reference is right; this is stated as an assumption;
- S-excl: the models' consensus status distribution, by exclusion reason, to describe what exclusion removes.

## Human packet

120 items (20 per stratum, seed 20261109), shuffled, as Markdown files with the same inputs and question, an answer-sheet CSV, and the key in `evidence/v12-wpk5/human-packet-key.json` outside the packet folder. `tools/v11/score_wpk5_human.py` computes κ against the reference and the models once filled sheets exist.

## Expectations stated before calls

- Agreement is highest on S-aligned and lowest on S-dis.
- On S-miss, suspects, if any, lower rather than raise the missed count.
