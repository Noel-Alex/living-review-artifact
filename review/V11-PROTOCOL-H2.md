# V11 H2 protocol: real-history evaluation on the 20 selected student repositories

Written by the lead on 2026-11-01 before any H2 observation exists. Local timestamped protocol, not an external registration. `evidence/v11-wph2/protocol-freeze.json` records this file's SHA-256, the H2 code hashes, the frozen B1 variant hashes (re-verified) and the UTC freeze time, before any start record.

## Inputs

- The 20 repositories S1–S20 of `evidence/v11-wph/private/selected.json`, read from the existing full-history clones in `evidence/v11-wph/private/tmp/<repository_id>`. Each clone's `HEAD` must equal the pinned `head_commit_sha`; otherwise that repository is reported unavailable. No new clone, no network, no checkout, no execution of repository code.
- Selection and reference: the original real-history harness (`evidence/source-snapshot/real_history.py` through `tools/regenerate_history_selection.harness`), unchanged: first-parent commits from the pinned head, horizons 1 and 10, eight anchors per sampling scheme per pair, three per file, files of 60–1,500 lines, the syntax-tree oracle with its ambiguity exclusions and the identical-copy exclusion. One `random.Random(20261028)` stream is consumed across repositories in S1…S20 order, as the original `main` did across its repositories.
- Python ≥ 3.12 (as the archived oracle and WP B1). Files the interpreter cannot parse yield no candidates, as in the original harness; their number is reported.

## Methods and metrics

- Every observation is evaluated with `run_wpb.evaluate_batch` unchanged: the eight frozen IG/AG/VW combinations at θ 0.85 and 0.55 (the deployed cascade is `t0.85-deployed`), cascade v1, exact quotation, diff drift, line number (baselines receive Git rename detection, the cascade does not), and the unchanged contextual tracker binary with WP A's re-check adapter. Tracker execution failures stay in all-target denominators.
- Metrics, denominators and Wilson 95% intervals are WP A/B1's (`analyze_wpb.event`, `DENOMS`). Report overall, by sampling scheme (uniform / edit-targeted), by horizon and per repository, with cluster-bootstrap 95% intervals by commit pair (10,000 resamples, seed 20261031) for the deployed-cascade accuracy and missed re-check rate and for the paired difference deployed − tracker.
- Exclusion counts per reason, pairs, observations per repository and the share of observations each repository contributes are reported. Results from repositories with fewer than 30 observations are shown but flagged.

## Interpretation

This is a held-out evaluation for every method: no threshold, guard or design was chosen on these repositories. It is a public student-authored stand-in, not supervised capstone resubmissions; commits are not submissions, and the oracle is the same syntax-tree heuristic as the original real-history study, not human annotation.
