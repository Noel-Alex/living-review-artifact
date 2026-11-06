# V11 Protocol J: a language-model locator inside the safety layer

Registered by the lead on 3 November 2026, before any evaluation call. The protocol text and the WP J code are frozen by SHA-256 in `evidence/v11-wpj/protocol-freeze.json` before the first evaluation call. Only the 20 development observations named in `evidence/v11-wpj/export.json` (`dev`) may be sent to the model before the freeze. They come from the public open-source uniform sample, which is not an evaluation population.

## Why

- Related systems re-anchor annotations with a language model (Magic Markup, Codetations). The paper cites them but runs no language-model locator, so a reviewer will expect that comparison.
- Section XII argues for a replaceable locator under a fixed safety layer. It was tested with CodeMapper and the contextual tracker; a language model is a different kind of locator.
- The portal's rule is that AI is advisory and faculty decide. That raises a direct question: is a language model's own judgement of whether code changed a safe re-check signal, or does the locator-independent safety layer still matter when the locator is a language model?

## Model and settings (fixed)

- Model `stepfun/step-3.7-flash:free` (open weights, `stepfun-ai/Step-3.7-Flash`), called through the local Hermes proxy (`hermes proxy start --provider nous`, OpenAI-compatible, Nous Portal free tier). It is the free model of the StepFun family the Hermes configuration uses. Paid models are unavailable (no credits), and no model runs locally.
- `temperature 0`, `seed 20261103`, `max_tokens 16000`, `reasoning.effort low`.
- Prompt `wpj-prompt-1` (`tools/v11/wpj_core.py`):
  - an old-version excerpt with 15 lines of context, the region's lines marked `>>`;
  - the complete new version of the paired file, line-numbered;
  - a fixed task asking for `{"status": "found"|"deleted", "start", "end", "changed"}`.
- Scope: one paired file, as CodeMapper's C6 input scope.
  - The paired file is the anchor's path in the new version, else its recorded rename, else (external rows) the benchmark's target file.
  - With no paired file, no call is made and the anchor is reported removed.
- A prompt over 700,000 characters (about the 262,144-token context of the model) is not sent; neither is a new file over 40,000 lines. It is recorded as an execution error, and that error stays in the denominators.
- **Retries.** Only transport failures are retried: HTTP 408/429/5xx, timeouts and connection errors, up to 8 attempts with backoff. An answer is never re-asked.
- **Invalid answers** are execution errors, which request re-check: a missing JSON object, a bad status or bad line numbers.
- Every raw response is kept in `evidence/v11-wpj/calls/`.

## Populations (public code only)

No private portal code, controlled-corpus file or internal-project history is exported or sent.

| Name | Observations | Source |
|---|---|---|
| `human-AB` | all 200 | CodeMapper human-annotated A and B, the paired-file inputs of WP I `external_scope` |
| `real-oss-targeted` | all 2,454 | the public open-source edit-targeted real-history sample (Requests, Flask, Click, HTTPX, Rich), from `run_wpc_c6.reused_inputs` with hash checks |
| `students-targeted` | all 1,857 | the targeted sample of the public student-authored repositories (WP H2 `students2`), from the pinned clones |

- **Order.** Populations are run in the order above.
- **Completeness.** A population is reported only when every observation has a recorded outcome; an incomplete population is reported as incomplete, with no rates.
- **Repeat.** `human-AB` is run a second time (pass 2) with identical settings, to measure run-to-run agreement.

## Methods (per observation)

- `llm-self`: the model's own judgement.
  - `deleted` is reported removed (re-check).
  - `found` with `changed=true` is reported changed (re-check).
  - `found` with `changed=false` is reported exact if at the original path and start, otherwise moved, with no re-check.
- `llm+quote`, `llm+IG`, `llm+AGi`, `llm+IG+AGi`: the model's window under the WP I locator-independent layers (`window_layers`, `window_layers_i`). These are the quotation labels plus the indentation guard and AGi, exactly as for CodeMapper. Placement is the model's, unchanged.
- **Comparators on the same rows.** These are already in the WP I evidence and are not re-run:
  - `codemapper+quote`, `codemapper+IG+AGi`;
  - the deployed cascade `t0.85-deployed` (as the WP I macros);
  - `t0.85-IG+AGi+VW`.

Scoring uses the WP C/WP I `ev` function and denominators unchanged: accuracy, placement, missed re-check, unnecessary re-check, wrong, wrong-silent and lost.

## Hypotheses (registered)

- **J1 (primary).** On each completed population, `llm+IG+AGi` has fewer missed re-checks than `llm-self`.
- **J2.** On each completed population, `llm+IG+AGi` has fewer silent misplacements than `llm-self`.
- **J3 (cost, two-sided, descriptive).** Unnecessary re-checks on preserved targets for `llm+IG+AGi` against `llm-self`.

**Test.** For J1 and J2: paired exact two-sided binomial test on discordant observations (McNemar framework), plus a cluster bootstrap 95% interval of the difference. The bootstrap uses 10,000 resamples, seed 20261031, clustered by commit pair. A hypothesis is supported on a population if the interval excludes zero in the stated direction. Each population is reported separately, with no pooling.

**Descriptive.**
- Placement accuracy of the model against CodeMapper and the deployed cascade on the same rows.
- The `changed` judgement against the reference class.
- Run-to-run agreement on `human-AB`, as the share of observations with identical placement and label in passes 1 and 2.
- Execution errors and invalid answers.
- Token use and latency.

## Limits stated in advance

- The model is a single free model served by a third party. Its serving stack may change, and the run reports a dated observation, not a property of language models in general.
- Prompts are fixed, not tuned on evaluation data; a different prompt may do better.
- The model sees one file, so it cannot follow code into another file, as CodeMapper cannot.
- The real-history and student references come from the syntax-tree oracle, not from people. Only `human-AB` has human references.

## Deviations

Any change after the freeze is a numbered amendment in `evidence/v11-wpj/protocol-amendment-N.json`, recorded before the outcomes it affects are read, and reported to Noel.

## Amendment 1 (3 November 2026, 04:45 UTC): rate limits

The free tier began returning HTTP 429 ("exceeded the rate limit on your API key") during `real-oss-targeted` pass 1, after 344 of 2,454 calls. Under the original rule a 429 counted as a transport attempt, so a long limit window would have turned observations into `transport_failed` execution errors that reflect the account's quota, not the model. The runner was stopped before any such record existed: every recorded HTTP error so far is a 451 provider refusal. No `real-oss-targeted` outcome was read; only response status counts were inspected.

- A 429 no longer counts as an attempt. All workers pause for 120 s and the call is resent, up to 2,000 times per call. Other transport failures keep the original rule.
- Each answered record stores `rate_waits`.
- Work resumes with 2 workers instead of 6, because the limit applies to the user's whole Nous key, which their own Hermes use shares.
- 451 refusals stay execution errors, as before.
- Prompt, model, settings, populations, methods and hypotheses are unchanged. Records already written are kept as they are.

## Amendment 2 (3 November 2026, recorded 05:27 UTC): primary model is the one the deployed portal uses

On Noel's instruction the primary model changes to `reflection/beam-1.0-501b-a23b:free` (Reflection Beam 1.0, open weights `reflection/Beam-1.0-501B-A23B`, 262,144-token context on the free tier). It is the model the deployed Vcap server is configured with (`HERMES_PROVIDER=nous`, `HERMES_MODEL=reflection/beam-1.0-501b-a23b:free`, read from the server's environment on 3 November 2026), called through the same local Hermes proxy and Nous Portal. Two reasons: it is the model a Vcap deployment would actually put behind the safety layer, so the result speaks to the system the paper describes; and it answers about six times faster (dev median 1.25 s against 7.0 s), so all three populations and the repeat pass can finish in one session instead of being cut short by the free-tier rate limit.

What had been read when this was decided: the complete Step-3.7-Flash `human-AB` pass 1 (layers, J1 to J3 and the comparator rows, an interim summary), and status counts only for the 727 recorded `real-oss-targeted` Step responses. No Beam evaluation call had been made. The switch was not chosen for an outcome: the hypotheses, prompt (`wpj-prompt-1`), settings (temperature 0, seed 20261103, `max_tokens` 16000, reasoning effort low), size caps, populations, methods, retry rules and Amendment 1 all carry over unchanged, and J1 to J3 are tested on Beam for every population.

- Beam calls, layers and dev records go under `evidence/v11-wpj/beam/` (`calls/<population>-pass<N>/`, `layers/`, `dev/`). Step records stay where they are, unchanged.
- The Beam dev check (the same 20 non-evaluation open-source observations) ran before this amendment: 20 of 20 valid answers, 10 `exact` and 10 `moved`, as for Step.
- Step-3.7-Flash is kept as a secondary model. Its complete `human-AB` pass 1 is reported as a cross-model check, labelled as the originally registered model and analysed with the same code. Its partial `real-oss-targeted` responses are not analysed and not reported as a result. Step's `students-targeted` population and repeat pass were never run.
- The summary reports Beam under `populations`, and Step under `secondary.step`.
- Workers: 4, with the Amendment 1 rate gate. The deployed portal may share the free-tier quota; if 429s appear, the gate pauses all workers.

## Amendment 3 (3 November 2026, recorded 05:29 UTC; protocol text re-hashed in record 4 after this time correction): rate-limit pause length

The Nous key's response headers show the binding limits: 50 requests and 500,000 tokens per minute, 2,100 requests and 6,000,000 tokens per hour, with an IETF `ratelimit` header giving the seconds to reset (`t=`). WP J needs about 38 million tokens (the prompt contains the whole new file), so the hourly token quota, not the model's latency, sets the run time. The fixed 120 s pause of Amendment 1 wastes quota windows. A 429 now pauses all workers for `Retry-After` seconds, else the header's `t=` plus 1 s, else 60 s, kept between 5 and 120 s. It is still not an attempt, still capped at 2,000 waits per call. The first Beam run had 27 `human-AB` records when it was stopped for this change, and none had been read. Those records are kept and the run resumes from them. No other rule changes.

## Amendment 5 (3 November 2026; the record time is in `protocol-amendment-5.json`): an exploratory third model on a separate quota

On Noel's request, the same frozen calls are also sent to Step 5 Preview (`stepfun-ai/step-5-preview`) through the NVIDIA API catalog (`https://integrate.api.nvidia.com/v1`, free, 1,048,576-token context). NVIDIA's quota is separate from the Nous key, so this runs alongside Beam without slowing it. It asks whether the registered contrasts hold for a second current model family, which one model cannot show.

- **Status.** Exploratory and secondary. Beam stays the primary model, and J1 to J3 are tested on Beam as registered. Step 5 is analysed with the same code and reported under `secondary.step5`, with no pooling across models.
- **Transport only.** The runner `tools/v11/run_wpj_nim.py` imports `run_wpj` and replaces only the endpoint, the model, the API key and the name of the reasoning setting: NVIDIA rejects the `reasoning` object (HTTP 400), so effort low is sent as `reasoning_effort: "low"`. Its SHA-256 is in the record's note.
- **Unchanged.** Prompt `wpj-prompt-1`, temperature 0, seed 20261103, `max_tokens` 16000, the 700,000-character and 40,000-line caps (so the same observations are sent), retry rules, Amendments 1 and 3, populations, order, completeness rule, repeat pass, methods and scoring.
- **Records** go under `evidence/v11-wpj/step5/`. The key is Noel's NVIDIA key and is never written to evidence.
- **Workers:** 6.
- **What was read before this amendment.**
  - Three probe calls on development observations, kept outside evidence. The first three were rejected for the `reasoning` object; of the next three, two were answered and one hit a 504.
  - The Step 5 dev check on the same 20 development observations: 20 of 20 valid answers, median 8.5 s, slowest 264 s, 4 transport retries (Beam: 20 of 20, median 1.2 s).
  - No Step 5 evaluation call had been made, and no Beam outcome had been read: only Beam status counts.
- **Limits.** Step 5 is a preview model behind a gateway that times out at about 300 s. Long prompts that time out on every attempt become `transport_failed` execution errors, which request re-check and stay in the denominators. If the preview is withdrawn before a population completes, that population is reported as incomplete, with no rates.
- **Code change.** `tools/v11/analyze_wpj.py` adds `step5` to the analysed models (`ALL_MODELS`). The amendment record carries the new code hashes.

## Amendment 6 (3 November 2026; the record time is in `protocol-amendment-6.json`): Step 5 Preview stopped after `human-AB`

Noel stopped the Step 5 run as too slow. Through NVIDIA's free gateway the median call took 36 s on `human-AB`, and `real-oss-targeted` was answering about two calls a minute, with calls failing after eight consecutive 504 timeouts. Finishing the remaining populations would have taken about 34 more hours.

- Step 5's complete `human-AB` pass 1 is kept and reported under `secondary.step5`, as Step-3.7-Flash's is.
- Its 255 `real-oss-targeted` records (253 answered, 2 `transport_failed`) are kept but not analysed or reported. Only their status counts were read.
- `students-targeted` and the repeat pass were never run for Step 5.
- Nothing else changes. Beam's complete run (all three populations and the `human-AB` repeat) was analysed under the registered rules before this amendment. The Beam result does not depend on this change.

## Amendment 7 (3 November 2026; the record time is in `protocol-amendment-7.json`): a faster second model on every population

After Step 5 Preview was stopped (Amendment 6), Noel asked for a faster model served through NVIDIA. Nine models in the NVIDIA API catalog were timed on six development observations. The two fastest with valid answers were then given the full 20-observation dev check. The choice rule: all 20 valid, then the lower median latency.

| Model | Valid | Median | Slowest | Retries / rate waits |
|---|---|---|---|---|
| `nvidia/nemotron-3.5-super-vl-120b-a12b` (NVIDIA Nemotron 3.5 Super, 1,048,576-token context) | 20/20 | 2.4 s | 41.6 s | 0 / 0 |
| `minimaxai/minimax-m3.1-flash` | 20/20 | 8.2 s | 46.1 s | 1 / 3 |

- Nemotron 3.5 Super is run on all three populations and the `human-AB` repeat, in the registered order. It is a secondary, exploratory model, reported under `secondary.nemotron` with the same analysis code. Beam stays the primary model, and J1 to J3 are tested on Beam as registered. The same contrasts are reported for Nemotron, so the cross-model question can be answered on all populations, not only `human-AB`.
- The transport is the one in Amendment 5 (`tools/v11/run_wpj_nim.py --model nemotron`, `reasoning_effort: "low"`). Every other rule is unchanged.
- Records go under `evidence/v11-wpj/nemotron/`. MiniMax's dev records are kept under `evidence/v11-wpj/minimax/dev/` and not used further.
- **Workers:** 4, with the Amendment 1 and 3 rate gate.
- **What was read before this amendment:** the complete Beam analysis (`summary-20261103T182647.json`), Step 5's `human-AB` analysis, and dev checks only for the candidates. No Nemotron evaluation call had been made.
- **Code change:** `analyze_wpj.py` adds `nemotron` to `ALL_MODELS`.

## Amendment 8 (3 November 2026; the record time is in `protocol-amendment-8.json`): Nemotron 3.5 Super stopped; Beam alone

Noel stopped the Nemotron run: Beam's complete run answers the registered questions, and no further model is needed. NVIDIA's free gateway was also rate-limiting `real-oss-targeted` to about one call a minute.

- Nemotron's records are kept under `evidence/v11-wpj/nemotron/`: `human-AB` pass 1 (200 records), `real-oss-targeted` pass 1 (1,040 of 2,454) and `students-targeted` pass 1 (1 record). No layers stage was run and none of them is analysed or reported. Only record counts were read.
- No further model is run. The reported study is Beam (primary, all populations and the `human-AB` repeat), with Step-3.7-Flash and Step 5 Preview as secondary models on `human-AB` only, as before.
- No code changes. `analyze_wpj.py` reports a model only where its pass-1 layers exist, so Nemotron appears as incomplete.
- **What was read before this amendment:** the complete Beam analysis (`summary-20261103T182647.json`) and the secondary `human-AB` analyses for Step-3.7-Flash and Step 5. No Nemotron outcome was read.

## Amendment 9 (3 November 2026; the record time is in `protocol-amendment-9.json`): Nemotron resumed, superseding Amendment 8

Noel clarified that he wants the most useful study, and a second model on every population is useful: a single-model result cannot show whether J1 to J3 hold beyond Beam. Amendment 8 is withdrawn and Amendment 7 applies again.

- The run resumes from the saved records. `run_calls` skips identifiers that already have a record, so no call is repeated and no record is overwritten. The remaining order is unchanged: `real-oss-targeted` pass 1 (1,414 left), `students-targeted` pass 1, then the `human-AB` repeat, then the layers stage for each.
- Settings, workers (4) and the rate gate are Amendment 7's. Under NVIDIA's rate limit the run made about five calls a minute, so it is expected to take about 12 hours.
- **What was read between Amendments 8 and 9:** record counts and the progress log only. No Nemotron outcome had been read.
