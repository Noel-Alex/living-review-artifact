# WP K7 protocol: ReviewAnchorBench as an external evaluation source

Status: lead-written 6 Nov 2026, before any locator outcome on these cases was read. The frozen record is `evidence/v12-wpk7/protocol-freeze.json`. It holds the SHA-256 of this file, of the code (`tools/v12/rab_cases.py`, `tools/v11/run_wpk7.py`, `tools/v11/analyze_wpk7.py`, plus the reused frozen layer modules) and of `evidence/v12-wpk7/units.json`. A smoke run on at most 20 cases checks execution only and is never analysed.

## Purpose

Professor review R02, item Lit-1, asked for ReviewAnchorBench to be considered as an additional external evaluation source. Its cases were built by people outside this project and come with mechanical oracles. K7 runs the paper's locators and safety layer on those cases and scores them with the paper's six outcomes. K7 also re-scores the benchmark's own released per-case predictions under the same outcomes.

## Source

- ReviewAnchorBench replication package 1.1.0: Zenodo DOI 10.5281/zenodo.22217751, CC-BY-4.0 data, MIT code. The zip has SHA-256 `d56601eb3ab0c4bd3d4b5d2ef7dd096538ca797909f726ab16a2c50869183fd9`.
- The accompanying paper is a preprint. It is not cited, per the professor's no-preprint rule; the dataset is cited.
- Strata:
  - the population-sampled stratum: 300 anchors, 3,000 cases, `results/review_anchor_population_sampled_benchmark_v3.json`;
  - the hard held-out split of the v1 benchmark: 379 anchors, 3,790 cases, `results/review_anchor_benchmark_v1.json`, split `HELD_OUT_TEST`.
  - The benchmark's calibration split is not used.
- Source files are fetched from the pinned raw GitHub URLs in `inputs/third_party_evidence_manifest.json`. Each is checked for size and SHA-256 by `tools/v12/rab_fetch.py`, giving `evidence/v12-wpk7/fetch-report.json`.
  - 705 of 756 verified. 51 return HTTP 404 upstream; those cases are excluded and counted.
  - The blobs are fetch-only under the benchmark's licence policy. They are never redistributed.

## Case reconstruction (deviation from the plan, recorded before any outcome)

The benchmark's transformation builder (`build_review_anchor_benchmark.py`) is in neither released package (1.0.0 nor 1.1.0). `tools/v12/rab_cases.py` therefore rebuilds each target file from the source blob and the case's recorded family and parameters.
- A case is accepted only when the rebuilt file's SHA-256 equals the released `target_content_sha256` and its line count equals `target_line_n`. Nothing is approximated.
- Seven families rebuild exactly from their recorded parameters: IDENTITY, PREFIX_INSERT, BLOCK_MOVE, REPLACEMENT_APPLIED, MOVE_AND_REPLACE, TARGET_DELETE and DUPLICATE_PREIMAGE.
- Three families insert generated text that the descriptors do not record: INTERNAL_LINE_EDIT, SURROUNDING_CONTEXT_EDIT and WHITESPACE_INSIDE.
  - A bounded search over marker forms found no rule that reproduces the released hashes.
  - These three families are excluded from the locator runs and counted.
- Evaluable: 294 × 7 = 2,058 population cases and 375 × 7 = 2,625 held-out cases.

## Methods

Run here, from one CodeMapper execution per case, on the file pair (source → target, same path). The code reuses the frozen WP I/K6 layer code unchanged (`run_wpk7.py`, adapted from `run_wpk6.py`).
- `t0.85-deployed`: the deployed cascade.
- `t0.85-IG+AGi+VW`: the cascade with the safety layer.
- `codemapper+quote`, `codemapper+IG+AG` and `codemapper+IG+AGi`.

Re-scored from the benchmark's released records (supplied results, not rerun here):
- `rab-cascade`: FULL_DUAL_ANCHOR_CASCADE_V3, threshold 0.90, margin 0.05.
- Mapping:
  - LOCATED with state PREIMAGE → placement, no request;
  - LOCATED with state OTHER or REPLACEMENT → placement and request (it reports changed content);
  - DELETED or ABSTAIN → request, no placement.
- The benchmark's own CodeMapper records are used only to check agreement with this run's CodeMapper start lines.

## Outcomes

The class mapping follows K6's six outcomes (`analyze_wpk6.events`, imported unchanged):

| Family | K6 class | Truth |
|---|---|---|
| IDENTITY, PREFIX_INSERT, BLOCK_MOVE | untouched | oracle range start |
| REPLACEMENT_APPLIED, MOVE_AND_REPLACE | applied | oracle range (replacement span) |
| TARGET_DELETE | applied-deletion | none |
| DUPLICATE_PREIMAGE | ambiguous | request rate only |

Primary measures:
- missed re-checks on changed cases (applied plus deletion);
- silent wrong placements;
- unnecessary requests on untouched cases;
- the request rate on duplicates.

Placement and lost are secondary. Execution errors count as requests without placement and are reported in their own column.

`rab-cascade` is also scored on all ten families, a secondary table:
- INTERNAL_LINE_EDIT is a changed class with truth at the oracle range (applied semantics);
- SURROUNDING_CONTEXT_EDIT is untouched;
- WHITESPACE_INSIDE reports placement and request rates only.

## Statistics

- Wilson 95% intervals.
- Repository-cluster percentile bootstrap (10,000 resamples, seed 20261106) on the seven-family cases, for these paired differences:
  - IG+AGi+VW − deployed;
  - codemapper+IG+AGi − codemapper+quote;
  - IG+AGi+VW − rab-cascade;
  - codemapper+IG+AGi − rab-cascade.
- Each stratum is reported separately. The strata share 126 anchors, so they are not pooled.

## Expectations (stated before outcomes, not hypotheses with a test)

- The layer should cut missed re-checks against the deployed cascade, as on K6.
- Because `rab-cascade` searches for the replacement as a second anchor, it can report applied replacements as changed. Its misses should concentrate where neither anchor is found intact.

## Limits

- The edits are synthetic and the files public. Families with generated text are absent from the locator runs, so the hardest within-span edit (INTERNAL_LINE_EDIT) is scored only for `rab-cascade`, from its released records.
- The benchmark's sources are bot-authored suggestions, not student submissions.
- `rab-cascade` numbers are the benchmark authors' released outputs, re-scored here, not reproduced.
- The benchmark assigns the replacement span as the truth for applied cases. The paper's layer has no access to the replacement text; it is scored on the same oracle.
