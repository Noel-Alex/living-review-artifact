# V12 WP K1 protocol

Recorded: 2026-11-06. This is a retrospective, post-hoc descriptive re-aggregation of saved WP I and WP J records; all records have already been read. It is not held out, not a preregistration, and provides no confirmatory inference. No new locator runs are authorized. Saved evidence is read-only. Any change after freezing will be documented in `evidence/v12-wpk1/protocol-amendment-N.json` before reading affected results.

## Frozen populations, configurations, and outcomes

Use `analyze_wpi.load` semantics for transfer (including Amendment 2 external-cascade replacement), compound, students2, fresh and chains; merge the saved AGi rows exactly as `analyze_wpi.main` does. Include WP J rows only for its recorded populations (`human-AB`, `real-oss-targeted`, `students-targeted`) and only configurations present in each record. Never impute absent cells. For the six issue outcomes, preserve each WP I event and denominator independently: placement accuracy, missed re-check, silent misplacement, misdirected request, lost and unnecessary re-check. Also report gone-kept and overall correct. Use the Wilson 95% interval. Contrasts use paired cluster bootstrap, 10,000 resamples, seed 20261031, with WP I `cluster_key`; chains cluster by chain.

Population labels are fixed as: fresh stress (all suites, plus duplicates, indentation and short separately); controlled replication; real histories (all); student-authored repositories; external human-annotated (`external:human-AB`); fresh compound k=4; and ten-hop chains. The six outcomes are reported only when both the population and configuration exist.

## Deployment policies and selection

Candidate policy set is frozen to every saved configuration available within a population: each cascade locator/layer/threshold recorded in WP I plus each recorded CodeMapper, tracker, hybrid and WP J model configuration. Execution failures remain in their original denominators and event coding. Pareto dimensions are per-target rates for (missed + silent), misdirected, lost, and unnecessary re-check. A policy is Pareto dominated only if another is no worse in all four dimensions and strictly better in at least one.

For each population and candidate, compute `C = w*(missed + silent) + m*misdirected + unnecessary + lost`, using the corresponding WP I denominators and rates per carried target; unnecessary confirmation has unit cost. Evaluate all `w in {1,3,10,30}` and `m in {1,3}`. Ties resolve by lower C, then lower missed+silent, then fewer execution errors, then lexicographic configuration name.

Leave-one-project-out uses the nine real-history `repo` groups; leave-one-repository-out uses student `repo` groups. Choose the candidate with minimum pooled C on training groups; evaluate pooled held-out C and six outcomes. Compare regret to the held-out oracle and fixed deployed cascade / CodeMapper+IG+AGi, where available. Cross-population selection uses the same rule on each complete source population, evaluates every applicable destination population, and reports unavailable pairs explicitly. Stability means the share of folds selecting the modal exact policy; out-of-sample improvement is paired descriptively against each fixed default.

## Strata and misdirection

Anchor span bins are fixed as 1, 2-3, 4-9, and >=10 lines. Old-version identical normalized-quotation copy counts exclude the anchor and use bins 0, 1, 2-3, >=4. Nearest-copy distance bins: same file within 20 lines, same file farther than 20 lines, or other file. Derive from pinned old trees using the read-only paths and loading logic in `run_wpi.py`/`wpa_core.loaders`/`history_context`. Report missed, silent, misdirected and unnecessary outcomes for deployed cascade, cascade+IG+AGi+VW, CodeMapper+quote, CodeMapper+IG+AG and CodeMapper+IG+AGi. Confidence/guard table uses cascade `tier` and stored similarity if available, guard fired iff `reasons` is nonempty; CodeMapper uses its stored confidence field, otherwise report no confidence field. Multi-anchor issue outcome groups only where saved row keys establish a shared issue; a returned issue has any anchor request. Otherwise state unsupported by these records.

For misdirected and silent-wrong outputs, report same-file share, truth-line distance median/IQR, and whether truth is among identical copies of the shown quotation in the new version plus candidate-set size. Three-way output is verified (placement and no request), ambiguous (copy-guard request; all identical copies are candidates), or missing (no placement). Report truth hit rate and candidate-set size for each.

## Identity-floor sweep and consistency check

Replay `identity_hop` over each saved `-id` trace: floors 0.50-1.00 by 0.05 from `-id`, floors 0.30-0.50 by 0.05 from `-id0.3`; replay decisions per hop until the first divergence. Gate replay 0.7 from 0.5 against stored `-id0.7`, and replay 0.5 from 0.3 against stored `-id`; report exact mismatches. On any non-exact gate, cascade may be recomputed with existing cascade chain code; CodeMapper remains replay-only and its limitation is explicit. CodeMapper `cm-seq-id` and `cm-seq-gi-id` are replayed from 0.5 upward only. At h=10 report correct, wrong, lost, missed-last, silent-wrong endpoints. Changed-hop ratio distributions are split by reference target versus wrong window, where prefix reference exists. Extreme-floor failure mechanisms include counts and 3-4 row ids each. Consistency check traces `smCtlCasAccPct` and `smCtlCasPlacePct` to their builder and states outcome, denominator, and seed.

## Reporting

All numbers are descriptive and carry their true denominators. Preserve failures and unavailable cells. Record input hashes, analysis code hash, protocol hash and UTC time in each summary/provenance artifact. Do not edit protected WP I/J evidence or WP K6 files. No changes to v11/v12 manuscript sections. Rebuild v12 as specified and compile all K1 floats in a scratch LaTeX document using the v11 preamble. All output remains within `paper-drafts/`.
