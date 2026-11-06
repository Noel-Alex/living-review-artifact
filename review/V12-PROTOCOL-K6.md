# WP K6 protocol: suggestion-application oracle

Status: lead-written (6 Nov 2026). It replaces the unfrozen worker draft. The frozen record is `evidence/v12-wpk6/protocol-freeze.json`: SHA-256 of this file, `review/briefs/WPK6-decisions.md`, the code and `units.json`, recorded before any locator outcome is read. A smoke run on at most 20 units checks execution only and is never analysed.

## Purpose

An independent, mechanically checkable reference in several languages for carried review comments (professor review Team02_R02, items 1, 3 and 7). A GitHub suggestion comment carries two anchors: the quoted original lines O and the reviewer's proposed replacement S. At the PR's final head, the oracle classifies what happened to the reviewed code. The reference was not made by the authors, and no annotator is involved.

## Rules

Decisions D1–D9 in `review/briefs/WPK6-decisions.md` are part of this protocol. In summary:
- **Selection.** Ten repositories, two per language (Python, TypeScript, Go, Rust, Java): the most-starred with a permissive licence and at least 40 eligible units among their 400 most recently updated PRs merged from 2024-01-01 to 2026-06-30. The cap is 250 units per repository, chosen by a seeded hash.
- **Unit.** The first comment of a review thread, on the RIGHT side, with exactly one suggestion fence.
- **Revisions.** c0 is the comment's original commit and c1 the PR's last head.
- **Normalization.** Strip each line and drop blank lines, as the cascade does.
- **Rename.** Detected by GitHub's compare API.
- **Classes.** gone-file, applied-deletion, applied, untouched, ambiguous, rewritten.

Deviation D1a (lead, before any outcome): the candidate walk is limited to the 40 most-starred repositories per language; a language with fewer than two accepted repositories is reported with what it has. The first run's 15-candidate walk accepted too few (Python 1, TypeScript 0, Java 1), and its resolution step crashed on a concurrent cache write, fixed by atomic writes. Both runs' logs are kept (`mine-run*.log`).

Deviation D2a (lead, before any outcome): units are restricted to source-code files by extension (`CODE_EXT` in `wpk6_mine.py`). Documentation and configuration files are excluded and counted, because the paper concerns code.

## Methods

The deployed cascade (`t0.85-deployed`); the cascade with IG+AGi+VW at θ=0.85; CodeMapper+quote, +IG+AG and +IG+AGi, all from one CodeMapper execution per unit. The scope is the file pair. The GitHub baseline is the thread's current `isOutdated` and `line`. Code: `tools/v11/run_wpk6.py`, which reuses the frozen WP I layer code unchanged.

## Outcomes (D6)

| Class | Correct behaviour | Scored |
|---|---|---|
| applied | request; placement inside the S occurrence | missed, placement, silent, misdirected, lost |
| untouched | no request; placement at the O occurrence start | unnecessary, placement, silent, misdirected, lost |
| applied-deletion, gone-file | request; no placement | missed; gone-kept (placed, no request); misdirected (placed, with request) |
| rewritten | request | missed only |
| ambiguous | — | request rate only |

Execution errors are reported in their own column and count as requests without placement, as WP I does. Rates are also given excluding errors.

## Statistics

Wilson 95% intervals. PR-cluster percentile bootstrap (10,000 resamples, seed 20261031) for paired differences against CodeMapper+quote and against the deployed cascade. Results are reported per language. The ambiguous stratum is reported separately.

## Claim-relative signal (D8)

The prompts are frozen verbatim in D8. They are run on the stratified applied and untouched sample, in the oracle-placement arm. Beam is primary and Nemotron secondary. The signal never resolves or keeps an issue.

## Limits

- Suggestions select small, concrete concerns.
- Matching final text does not establish the history in between.
- GitHub's outdated flag is read now, not at c1.
- Scope is restricted to the file pair, so cross-file moves are out of scope.
- "Applied" means the suggested text is present, not that the reviewer agreed.
