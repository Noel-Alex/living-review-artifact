# V11 WP I protocol: a stronger locator inside the safety workflow

Registered by the lead on 2 November 2026, before any WP I output exists. Frozen by SHA-256 together with the WP I code in `evidence/v11-wpi/protocol-freeze.json`. Executed by the lead (Codex unavailable).

## Why this package exists

Professor review R02 (2 November 2026) asks for four things: fix the pre-existing-copy guard's insertion defect, evaluate a stronger locator (CodeMapper) inside the safety workflow, preserve original-anchor identity across versions, and validate with people. The last is out of scope (Noel, 31 October 2026: no human studies). The reviewer's hypothesis is: *can the safety-oriented workflow improve the reliability of an already strong code-location algorithm?*

## What was already known when this protocol was written (not held out)

- WP C6 (registered extension, complete) applied the frozen B1 guards IG and AG to CodeMapper, GumTree, the contextual tracker and a tracker/cascade hybrid on the B1 stress suites (seed 20261027), the controlled replication, all 15,064 real-history observations, the public edit-targeted subset and the external CodeMapper benchmark. The lead has seen C6 aggregate results for CodeMapper (quote, IG, AG, IG+AG layers). They are reported as C6, not as WP I findings.
- WP B2 found the AG defect on compound edits: pinned `expected_start` maps an anchor whose preceding lines were inserted to the first inserted line, so an unmoved anchor is never "at expected"; AG also flags every within-file move by design.
- WP B2 chain results: last-hop labels miss 56.9% of changed endpoints because a `changed` hop rewrites the quotation, and 82 chains end wrong with last label `exact`.
- CodeMapper has not been run on the compound suite, the student repositories (WP H2) or the revision chains. No WP I guard (AG2) or identity rule has been evaluated on any population.

## I1. AG2: provenance-aware pre-existing-copy guard

AG2 replaces AG. Like AG it acts only when the locator returns an *exact window*: a window whose stripped non-blank lines equal the anchor quotation's. Changed windows already request re-check.

Definitions, for anchor path P, zero-based origin o, stripped quotation W, old version O, new version N, candidate file F and exact window start s:

- `runs(text)`: the pinned tier-2 run finder (`wpa_core.runs`) for W.
- `M_F`: `difflib.SequenceMatcher(None, strip(O[F]), strip(N[F]), autojunk=False).get_opcodes()` over per-line `str.strip()` text. A new line j is the *image* of old line i if both lie in one `equal` block at the same offset.
- *image run*: the window is the image of old run r if new line s is the image of old line r and r starts a run of W in O[F].
- *origin intact*: old line o has an image s_o in N[P] and s_o starts a run of W in N[P].

Decision for an exact window, evaluated in order:

1. **Copy count fell.** If F = P, O[P] is available, `|runs(O[P])| >= 2` and `|runs(N[P])| < |runs(O[P])|`: request (`copy-count-decreased`). An identical copy disappeared, so content cannot tell which copy survived.
2. **No previous text.** If F = P and O[P] is unavailable: request iff `|runs(N[P])| >= 2`. If F ≠ P and F is absent from O: accept (new file).
3. **Image of an old run.** If the window is the image of old run r: accept iff F = P and r = o (the anchor's own lines, possibly shifted); otherwise request (`pre-existing-copy`).
4. **New text.** Otherwise the window is newly inserted text: request iff origin intact (`duplicate-added`, since the anchor is still in place); otherwise accept (moved).

An all-blank quotation is requested (`blank-quotation`). An accepted window keeps the locator's label (`exact` if at the original start, else `moved`). A requested window is labelled `moved` with re-check, as AG does. IG is unchanged and composes with AG2 exactly as with AG.

**Cascade with AG2.** For the cascade, when tier 2 finds same-file runs, AG2 mode selects the image of the origin run if one exists, otherwise the deployed nearest-to-origin run. Then the AG2 decision applies. Fuzzy and cross-file tiers, VW, thresholds and `expected_start` for the fuzzy window are unchanged. Names: `t0.85-IG+AG2+VW`, `t0.55-IG+AG2+VW`, `t0.85-AG2`, `t0.85-IG+AG2`.

**Locator-agnostic family.** For a locator output b, the layers are `b+quote`, `b+IG`, `b+AG`, `b+IG+AG` (C6 definitions, recomputed as a gate) and `b+AG2`, `b+IG+AG2` (new). They apply the C6 `safety_family` window rules with AG2 substituted for AG.

## I2. Transfer to every existing C6 population (retrospective)

Inputs are regenerated through the C6 generators (`run_wpc_c6.stress_inputs`, `run_wpc_c6.reused_inputs`), which verify file hashes against the saved rows. Saved C6 base outputs (`c6_bases`) are re-used; no locator is re-executed. **Gate:** recomputed `b+quote`, `b+IG`, `b+AG`, `b+IG+AG` for all four locators, and the cascade `t0.85-IG+AG+VW` and `t0.55-IG+AG+VW`, must equal the saved C6 rows in label, placement and re-check for every observation. A gate failure stops the stage. Where a saved frozen cascade family recorded an execution error (the C1–C5 60-second boundary on large external files), the cascade AG2 variants are recorded as the same error and not re-executed.

## I3. New CodeMapper executions

CodeMapper runs at its pinned commit, unchanged, with the C6 `native-readonly` resolver and worker (`wpc_cm_worker.py`); the contextual tracker uses the frozen adapter. Execution failures are kept in denominators.

- **I3a Compound edits.** The 2,400 B2a trials (seeds 20261018 and 20261027, k = 1–4), regenerated under Python 3.11.4 (as B2a) and verified against the saved `compound/trials.json` metadata, then materialized as two-commit fixtures as in C6.
- **I3b Student repositories.** All 7,882 WP H2 observations on S1–S20, mapped in the pinned clones at their recorded commit pairs (read only).
- **I3c Fresh held-out seed 20261102.** B1 stress suites (indentation, duplicates, short; `b1a`, `duplicates`, `short`) and B2a compound edits (k = 1–4, 300 per k), generated only after this freeze, under the CodeMapper interpreter (Python 3.12.14). Methods: frozen cascade families and baselines via `run_wpb.evaluate_batch`, CodeMapper, tracker, and all I1 layers. This is the only population on which AG2 and CodeMapper-with-guards are both held out.

## I4. Identity-preserving anchors on revision chains

Population: the 4,000 archived ten-hop chains with the B2 prefix references (`evidence/v11-wpb2/chains/trials.json`), h ∈ {1, 2, 3, 5, 10}. References are re-used, not recomputed.

**Identity rule (ID).** Every carried anchor keeps the original quotation q0 (immutable) beside the current quotation q (replaced at `changed` hops as deployed). At each hop, after the base relocation:

- *Drift bound*: if the hop accepts a non-exact window, the window must also satisfy `ratio(q0, window) >= 0.5` (the same `SequenceMatcher` ratio on space-joined stripped lines as tier 3); otherwise the anchor is reported removed (visible loss). 0.5 is the calibrated threshold of the deployed analysis; 0.3 and 0.7 are reported as sensitivity only.
- *Reviewed-text request*: the hop requests re-check iff the base requests it or the located window's stripped lines differ from q0's.

Variants, all sequential over ten hops: cascade `v0.85-off`, `v0.85-all` (IG+AG+VW), `v0.85-all2` (IG+AG2+VW), `v0.55-all2`, each with and without ID; CodeMapper sequential (source region = previous hop's returned character region) with and without ID; CodeMapper direct (commit 0 → commit h) for each prefix.

Endpoint measures at each h, on decidable references: accuracy, wrong placement, lost, cumulative and last-state missed re-check, cumulative and last-state wrong-silent, and wrong-with-last-label-`exact`. For ID variants the last state is the reviewed-text request.

## Hypotheses and analysis

Primary (each judged per population; I3c is the held-out test):

- **H1 (reviewer's hypothesis).** CodeMapper+IG+AG2 has missed re-check and wrong-silent rates no higher than CodeMapper+quote and strictly lower on at least one, with placement unchanged by construction.
- **H2 (defect fix).** AG2 has fewer false re-checks than AG, for both the cascade and CodeMapper, without higher missed re-check or wrong-silent rates.
- **H3 (identity).** ID lowers h = 10 wrong placement and last-state wrong-silent relative to the same variant without ID; the cost is reported as additional lost anchors.

Statistics: Wilson 95% intervals; paired exact McNemar tests on discordant observations; 10,000 cluster-bootstrap resamples, seed 20261031 (clusters: source file for constructed suites, commit pair for histories, repository + commit pair for external data, chain for chains). Contrasts are nominal and not multiplicity-adjusted. A hypothesis "holds" on a population when the descriptive condition holds; it is "supported" when, in addition, the cluster 95% upper limits of the safety differences are at or below zero.

## Rules

- No change to frozen B1, B2, C or H2 code or evidence. WP I code lives in `tools/v11/wpi_*.py` and `tools/v11/run_wpi.py`; evidence in `evidence/v11-wpi/` (private inputs under `evidence/v11-wpi/private/`).
- Reporting code (`analyze_wpi.py`, `build_wpi_tex.py`) is written after the freeze, implements only the measures above and is hashed into its outputs.
- Every stage writes with exclusive-create; failures are recorded, not overwritten.
- Deviations after freeze are appended as dated amendments with a reason, and reported to Noel.
- Unit tests of AG2 use hand-built cases only (no evaluation data) and run before the freeze (`test_wpi.py`, 15 cases pass).
- A pre-freeze plumbing smoke (`smoke_wpi.py`) executed each stage's batch function once: eight development-seed-7 constructed trials, three C6 stress rows (gate only), two S1 observations and one chain. It printed only row counts, gate-mismatch counts (0) and execution-error counts (0); no outcome was inspected.

## Amendment 1 (2 November 2026, after freeze, before any WP I output was read)

CodeMapper does not follow code into another file unless Git reports a rename. A CodeMapper hybrid is added, defined exactly like the C6 tracker hybrid: `cmhybrid` takes the CodeMapper output, except when CodeMapper completed with no match and the deployed cascade's answer came from the cross-file tier (`cross_exact`); then the cascade's cross-file window is used. Its layers are computed in reporting code from outputs the frozen stages already produce: `cmhybrid+quote` uses the deployed output and `cmhybrid+AG2` / `cmhybrid+IG+AG2` use `t0.85-AG2` / `t0.85-IG+AG2` on fallback observations. On those observations both cascade variants also return the cross-file tier, since their fixed-window and cross-file tiers equal the deployed ones. On all other observations the CodeMapper layers are used unchanged. It enters H1 and the deployment comparison as an additional locator. No frozen code changes.

## Amendment 2 (2 November 2026, after the I2 gate, before any WP I outcome was read)

The I2 gate passed for every locator layer (CodeMapper, GumTree, tracker, hybrid; 43,406 observations) and for the cascade on all constructed and history rows. It failed for the cascade on 136 of the 2,392 external rows: the C6 input regeneration supplies the files predicted by every locator, while the C1–C5 cascade saw only the paired file (`input_scope = paired files only`), so the cross-file tier found copies the frozen run never saw. Stage `external-cascade` recomputes the cascade AG2 variants on external rows with the C1–C5 input scope (the target file in the new version, the source file in the old) and re-runs the cascade gate. Its outputs replace the transfer stage's cascade AG2 variants for external rows; locator layers are unchanged. The only code change is that stage.

## Amendment 3 (2 November 2026, after the first I3b run)

The first I3b run (`evidence/v11-wpi/students/`, retained) recorded CodeMapper execution errors on 7,451 of 7,882 observations: the H2 clones are blobless partial clones (`partialclonefilter=blob:none`), and CodeMapper's native Git diff needs blobs the cascade never read, while lazy fetching is disabled during mapping. Only execution-error counts were inspected to diagnose this. `acquire_wpi_student_objects.py` completes the objects of the 20 public repositories (refetch of the pinned head, no ref change, HEAD verified, no missing objects afterwards). I3b is then re-executed unchanged as stage `students2` (`evidence/v11-wpi/students2/`), which re-verifies every observation's file digests. The first run's cascade and tracker outputs had already been seen in aggregate; the `students2` run is reported, and the failed run is kept as an infrastructure record.

## Amendment 4 (2 November 2026, before any I3c held-out outcome was read)

Diagnosis on the first I3b run's cascade outputs (seen in aggregate): AG2 halves AG's false re-checks on student repositories but misses seven more re-checks than AG. All seven are one-line anchors whose single copy moved within the file while the syntax-tree reference called the statement edited or deleted; AG caught them only because it flags every within-file move. The reviewer's request was narrower: fix the insertion edge case. **AGi** is AG with exactly that fix: a same-file run at the image of the anchor's own old start (the stripped-line diff mapping of I1) counts as the predicted start, is preferred at tier 2, and is not count-tested. Everything else is AG. Layers `b+AGi`, `b+IG+AGi` for every locator, and cascade variants `t0.85-AGi`, `t0.85-IG+AGi+VW`, `t0.55-IG+AGi+VW` (external rows with the C1–C5 input scope), are computed by stage `agi` from the saved locator outputs on every population, including the held-out I3c seed. H2 is evaluated for both AGi and AG2 against AG; the paper reports both, AGi as the minimal fix and AG2 as the provenance rule. At the time of this amendment the I3c stage was still running and none of its rows had been read.

## Amendment 5 (2 November 2026, execution only)

The single-process `external-cascade` run was stopped after about two CPU-hours without output (no record was written). The same computation now runs over a process pool (`external_one`); inputs, functions and gate are unchanged.

## Post-hoc composition P1 (2 November 2026, exploratory)

After the AGi outcomes were read, `cmhybrid+IG+AGi` was composed from already-computed outputs: `codemapper+IG+AGi`, or `t0.85-IG+AGi+VW` when the Amendment 1 fallback fires. It adds no computation and is never counted toward H1 or H2. The manuscript reports it as exploratory.
Record: `protocol-amendment-6.json` holds the protocol hash with this note. The external-cascade stage checked the Amendment 5 hash at start. The P1 note was appended while the stage ran, so its output files record the later hash. The computation is the same.

## Amendment 7 (2 November 2026, chains with the recommended guard)

An internal review of the built manuscript found that the guarded rows of the ten-hop identity table used AG2 (`v0.55-all2`, IG+AG2+VW), and the guarded CodeMapper chain traces used IG+AG2, while the paper recommends AGi and reports AG2 as a negative result. AGi had never been run on chains. Stage `chains-agi` (`evidence/v11-wpi/chains-agi/`) re-runs I4 on the same 4,000 chains with the recommended guard: cascade `v0.85-alli` and `v0.55-alli` (IG+AGi+VW, `choose_i`), each with and without ID and with the 0.3/0.7 sensitivity floors, and CodeMapper sequential and direct with the IG+AGi layer (`cm-seq-gi`, `cm-seq-gi-id`, `cm-direct-gi`). Gates: `v0.85-off` must equal the B2 saved hops, and the labels-only CodeMapper traces (`cm-seq`, `cm-seq-id`, `cm-direct`) must equal the WP I `chains` stage exactly. H3 is evaluated for the new variants as registered in I4. The AG2 chain rows are retained and reported as the provenance-rule variant. Registered before any AGi chain outcome exists; the only outputs seen were a two-chain plumbing smoke's gate counts and a check that the refactored base mode reproduces the saved WP I rows byte for byte.

## Amendment 8 (2 November 2026, chains-agi gate outcome and reporting rule)

The `chains-agi` cascade gate passed on all 4,000 chains (`v0.85-off` equal to the B2 hops). The CodeMapper gate failed on 3 chains (rows 2086, 9093 and 10374): one sequential trace and five direct relocations differed from the WP I `chains` stage. Re-running those three chains three times in one process gave different CodeMapper outputs on identical inputs (end line 707 or 708 on row 9093; `removed` or `changed` at h = 10 on row 10374), so the pinned CodeMapper is not fully deterministic. Earlier WP I gates re-applied layers to saved CodeMapper outputs and never re-ran CodeMapper, so they could not detect this. Reporting rule, fixed before any AGi chain outcome was read: the AGi chain analysis (`chains_agi` in the summary) takes every CodeMapper trace (labels only, IG+AGi, direct) from the `chains-agi` run, so guarded and unguarded CodeMapper rows are paired within one run; cascade AG2 traces are taken from the `chains` stage, which is valid because the cascade reproduced exactly. The `chains` stage analysis is retained unchanged. The gate failure is kept on disk and reported in the paper.
