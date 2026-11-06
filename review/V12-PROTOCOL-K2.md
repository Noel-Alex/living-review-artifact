# V12 protocol K2: parametric copy and anchor suite (held out)

Answers professor review R02 items 9-10 (copy guard by duplicate frequency and distance; anchor length and anchors per issue). Frozen in `evidence/v12-wpk2/protocol-freeze.json` before any evaluated outcome exists.

## Inputs

- Corpus: the controlled stress corpus (`wpb_stress.corpus()`: `vcap/app`, `partners/cdc-trace/cdc`), the files the WP B and WP I stress suites use.
- Generator: `tools/v11/wpk2_suite.py`, seed **20261106** (not used by WP B, B2, C, I, J, K1 or K6; those used 20261018, 20261027, 20261031, 20261101-20261103). Each cell has its own generator stream (`random.Random(f"{seed}|{cell}")`).
- Smoke: `run --limit` uses seed 20261107 and one trial per cell; it checks execution only, and its outcomes are not reported.

## Design

- Factors: copies c ∈ {0, 1, 2, 4, 8}; placement of the nearest copy d ∈ {adjacent (0 lines between), near (1-20 lines), far (>50 lines), other file}; anchor height k ∈ {1, 2, 3, 5, 8}; fate ∈ {unchanged, shifted (1-5 comment lines inserted directly above), token edit, deleted}. c = 0 has no d. Full cross: 340 cells.
- Same-revision condition: no pre-existing copy; the original is token-edited or deleted, and the same revision introduces one copy at d (40 cells).
- 20 trials per cell: 7,600 trials. No fractional design is needed.
- Anchors: a run of complete statements of one body whose line extent is exactly k, starting with a non-comment line, whose stripped text occurs once in every file of the trial before copies are placed. Copies are verbatim, inserted at statement boundaries of a body with the same indentation. Extra copies (c > 1) go to same-file boundaries farther than the nearest copy or to boundaries in the 25 unrelated files of the trial, with equal chance.
- Checks per trial: every file of both versions parses (`ast.parse`); copy counts in both versions equal the design (stripped contiguous runs); the nearest-copy distance class is as designed. Rejected attempts are counted by reason in the generator audit.
- Reference: the original's location in the new version (none if deleted) and changed = fate ∈ {token edit, deleted} or same-revision.

## Methods

Deployed cascade (θ = 0.85, no guards); cascade IG+AG+VW and IG+AGi+VW at θ = 0.85; CodeMapper with the quote, IG+AG and IG+AGi layers. All CodeMapper layers come from one CodeMapper execution per trial (`native-readonly`). Execution errors are kept as outcomes (request, no placement). A Windows `PermissionError` while building a fixture is retried in a fresh folder, up to three times, before CodeMapper runs.

## Outcomes and analysis

- Six outcomes, as WP K1 and K6 define them: placement and lost over surviving targets; missed over changed targets; unnecessary over unchanged survivors; silent and misdirected over all trials. A placement is correct only at the reference start line.
- Main effects of c (all trials), d (c > 0) and k, by method; c × d for missed and unnecessary; the same-revision condition separately, by d, k and fate. Wilson 95% intervals.
- Multi-anchor issues: within each (c, d, k) group (same-revision: each (d, k)), trials ordered by (index, fate) form issues of 2, 3, 4, 2, 3, 4, ... anchors. An issue is missed if it holds a changed anchor and no anchor requests a check; unnecessary if no anchor changed and one requests; silent if any anchor is misplaced without a request.
- Paired differences: IG+AGi+VW − IG+AG+VW (cascade), CodeMapper+IG+AGi − +IG+AG, CodeMapper+IG+AGi − +quote, cascade IG+AGi+VW − deployed. Bootstrap over source-file clusters, 10,000 resamples, seed 20261031.

## Expectations stated before outcomes

- AGi requests fewer unnecessary checks than AG on shifted anchors, at an equal missed rate on pre-existing copies.
- Both guards miss the same-revision condition: the copy count rises, which is what a genuine move looks like.
- The deployed cascade's missed rate rises with c > 0 and is largest for adjacent copies.
