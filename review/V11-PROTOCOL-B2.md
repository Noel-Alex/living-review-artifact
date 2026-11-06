# V11 B2 protocol: compound edits, multi-hop prefixes, multi-anchor issues, complexity and scaling

Written by the lead on 2026-11-01 before any B2 result exists. This is a timestamped local protocol, not an external registration. `evidence/v11-wpb2/protocol-freeze.json` records this file's SHA-256, the B2 code hashes and the UTC freeze time; it must precede every B2 start record. The frozen B1 variant code (`tools/v11/wpb_variants.py`, `wpa_core.py`, `wpb_stress.py`, hashes in `evidence/v11-wpb1/protocol-freeze.json`) is reused unchanged; B2 verifies those hashes before running. A correction after freeze is a separately named post-hoc run that keeps both outputs.

Methods everywhere: deployed cascade (`t0.85-deployed`), the eight frozen IG/AG/VW combinations at θ = 0.85 and 0.55, cascade v1, exact quotation, diff drift, line number, and the unchanged external contextual tracker binary with WP A's re-check adapter. Metrics and denominators are WP A's `events`/`summarize` (Wilson 95%), with the explicit AG re-check flag substituted only for workflow-request metrics, as in B1. Failures and exclusions are counted, never dropped.

## B2a Compound edits

- Corpus, anchor sampler and unrelated-file sampling (up to 25) are the original controlled benchmark's (`wpb_stress.corpus`, `bench.pick_anchor`). Only `.py` files whose original text parses are sampled.
- Seeds: 20261018 + 303 and 20261027 + 303, reported separately. For each k ∈ {1, 2, 3, 4} and seed, at least 300 accepted trials; a 200,000-attempt cap reports an incomplete cell.
- Operators (sampled without replacement, applied in a random order, on line-tagged files so the anchored lines' identity is tracked by construction):
  1. `move-in-file`: the current anchored block moves at least 40 lines within its file.
  2. `move-file`: the block moves to a different, randomly chosen corpus file.
  3. `rename`: one identifier (`ast.Name`/`arg`/`Attribute` attr token) that occurs in the anchor is renamed, at every occurrence inside the anchor only, to a fresh name.
  4. `reformat`: AST-neutral layout change inside the anchor: one bracketed line is wrapped after a comma, or one continuation line is re-aligned; must leave the module AST unchanged.
  5. `expand`: one statement (`_wpb2_probe = None`, at the indentation of the following anchored line) is inserted strictly inside the anchor.
  6. `contract`: one non-first, non-last nonblank anchored line is deleted.
  7. `insert-above`: two to five statements are inserted immediately above the anchor at the anchor's first-line indentation.
  8. `token-edit-nearby`: one token on a nonblank line within five lines outside the anchor is mutated with the original `bench.mutate_token`.
- Every changed file must parse with `ast.parse` after the full composition, else the trial is rejected and counted by reason.
- Truth: final path and start = first surviving original-tagged anchor line; final end = last line of the tagged block including lines inserted inside it. Change class: the module-level statements (and function-body statements) whose line range intersects the anchor are dumped (`include_attributes=False`) before and after; unequal dumps = `edited`; otherwise `in place`/`shifted`/`moved file` by coordinates. This is construction plus syntactic AST truth, not execution equivalence.
- Report, per k, seed and method: placement accuracy, exact file/start/end range recovery (cascade-family methods with ranges only; never infer an end for line-only comparators), missed re-check, wrong-silent, wrong placement and lost. Also per operator-set membership (trials containing operator X) for the deployed cascade and the all-on variants. Curves are drawn in grayscale-safe matplotlib from the JSON.

## B2b Multi-hop prefixes

- Targets: the 4,000 archived horizon-10 chain observations (`evidence/revision-chains/trials.json`), unchanged.
- Prefix truth for h ∈ {1, 2, 3, 5, 10}: the original syntax-tree oracle (`evidence/source-snapshot/real_history.py`: `functions`, `candidates`, `oracle`, the same-height `changed` rule and the identical-copy exclusion), applied from the chain's first commit to commit h with Git rename detection (`--name-status -M`, `*.py`). Gate: recomputed h = 10 truth must equal every archived `truth_at` and `cls`; otherwise B2b stops.
- Prefix outcomes from the archived sequential traces (θ 0.85 and 0.5) at hop h, plus a fresh direct relocation from commit 0 to commit h. Gate: direct h = 10 must reproduce the archived direct outcomes.
- Variant chains: the frozen all-on combination (IG+AG+VW) at θ 0.85 and 0.55, and the zero-switch combination at θ 0.85 and 0.55 (same-θ comparators). The zero-switch θ 0.85 chain is a gate that must reproduce the archived default sequential trace (label and interval at every hop). Direct relocations from commit 0 to commit h are run for the deployed matcher at θ 0.85 and 0.5 and for the all-on and zero-switch variants at θ 0.85 and 0.55. Anchor update rule mirrors pinned `relocate_code`: removed keeps the stored anchor; hash-exact keeps it; otherwise path/start/end/content-hash come from the returned range, and the quotation is overwritten with the returned window only when the fuzzy tier placed it. When the previous file is unavailable the expected start is the stored origin, as in `expected_start(None, …)`.
- Report per h, on targets decidable at h and on the subset decidable at every h: endpoint accuracy, wrong placement, cumulative missed re-check (changed/gone by h and no request in hops 1..h), endpoint wrong-silent (wrong at h with no request in 1..h) and the last-hop-only variant of each. Endpoint references are not independent identity labels; intermediate AST references are the same heuristic, not human labels.

## B2c Multi-anchor issues

- Source: the frozen B1 evaluation records of all 15,064 real-history observations (`evidence/v11-wpb1/evaluation/`), per-observation deployed label and oracle class; no matcher rerun.
- For each commit pair and k ∈ {1, 2, 3, 5, 8, 12}, sample without replacement up to ⌊n_pair/k⌋ disjoint k-anchor groups (seed 20261101, pairs sorted, observations shuffled per pair). Distinct observation rows only; the first sampled anchor is the primary. Report the number of pairs and groups supporting each k.
- Issue-level outcomes: re-check rate (any anchor labelled changed/removed, or AG flag for the variant row), share of re-checks triggered only by non-primary anchors, primary-only-policy miss rate (some anchor changed or gone by the oracle, the primary's label requests no re-check, but the any-anchor rule does), and the issue-level missed re-check of the any-anchor rule. Grouping is synthetic: anchors in one commit pair are not known to belong to one review concern.

## B2d Complexity and scaling

- Analytic worst case per tier from pinned `carry.py`, in terms of file length L (lines), number of files F, anchor span s, radius r = max(10, 2s), quotation characters q, and SequenceMatcher's quadratic worst case.
- Benchmarks on this machine (CPU, Python version recorded): pinned public tags of django/django and CPython `Lib/` (full commit hashes recorded at download), plus the controlled corpus. Pairs of consecutive tags: django 5.1 → 5.2, CPython v3.12.0 → v3.13.0. Compositions of 1, 10, 100 and 1,000 anchors sampled with the original real-history candidate rule from changed Python files (seed 20261101), file maps limited to text `.py` files under 400,000 bytes as in carry. Report p50/p95 time per anchor and per composition (3 repetitions, after one warm-up), time share per tier, and peak traced memory (`tracemalloc`) for the deployed cascade and the all-on variant at θ 0.85. Adversarial tier-4 case: anchors whose quotation is absent from every file, so every other file is scanned.
- Timing is descriptive for one machine, not a performance guarantee.
