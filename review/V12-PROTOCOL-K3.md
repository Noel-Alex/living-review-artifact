# V12 protocol K3: supervisor interventions inside the ten-commit chains

Answers professor review R02 item 11 (multi-commit: supervisor interventions: correct anchor, accept change, dismiss). Frozen in `evidence/v12-wpk3/protocol-freeze.json` before the full run.

## Inputs

- The 4,000 archived ten-commit chains (`wpb2_chains.chain_rows()`), their prefix references at hops 1, 2, 3, 5 and 10 (`evidence/v11-wpb2/chains/trials.json`), and the stored `chains-agi` traces (`evidence/v11-wpi/chains-agi/rows.json`) for the P0 gate.
- Code: `tools/v11/wpk3_interventions.py`. The cascade hop, identity rule and CodeMapper sequential logic are copied verbatim from `run_wpi.chain_job` (frozen).
- Pre-freeze smoke: the first two jobs (50 chains) were run to check the P0 gate (0 cascade mismatches; 500/500 CodeMapper hops equal for each trace). Their outcomes were not analysed; the full run recomputes them.

## Simulated supervisor (an oracle)

The supervisor acts only at a prefix hop h ∈ {1, 2, 3, 5}, only when the method requested a check on that hop (a supervisor sees requests, not silent errors), and only when the reference at h is decided. Policies:

- **P0 none**: the stored traces.
- **P1 correct**: if the placement is wrong or lost and the reference has a location, re-anchor there with the code there as the quotation; under the identity rule the reviewed quotation q0 becomes that code too. If the reference says gone and the anchor is placed, stop carrying the anchor and keep the issue open (a visible gone: every later hop requests a check without a placement).
- **P2 accept**: if the placement is correct and the label is `changed`, the change is reviewed; under the identity rule q0 becomes the current code.
- **P3**: P1, otherwise P2.
- **P4 dismiss** at the first request; the issue is not carried further.

Each chain continues from the intervened state with the same method.

## Methods

Cascade deployed (`v0.85-off`), cascade IG+AGi+VW at θ = 0.85 (`v0.85-alli`) and θ = 0.55 (`v0.55-alli`), each with and without the identity rule (floor 0.5); CodeMapper+IG+AGi sequential, with and without the identity rule (`cm-seq-gi`, `cm-seq-gi-id`).

## Outcomes

At hop 10, over chains whose hop-10 reference is decided: correct, wrong and lost endpoints; silent wrong (wrong without a request at hop 10). Changes are measured **since the last supervisor review**: the last correct, accept or stop action, or the original review if none. Changed = the reference is gone at 10 (and was not at the review), or its stripped text at 10 differs from its stripped text at the review (stripped as the reference oracle strips). Missed-last = changed and no request at hop 10; missed-cumulative = changed and no request on any hop after the review. Effort: supervisor actions per chain, and requests seen at hops 1, 2, 3, 5 and 10. P4: dismissed chains, and how many had a reference change after the dismissal hop (changes the workflow will never surface, by design).

Paired chain-bootstrap differences of P1-P3 against P0 per method (10,000 resamples of chains, seed 20261031), as `chain_analysis` does.

## Gates

P0 must reproduce the stored `chains-agi` hops (label, interval, request) exactly for every cascade method. For CodeMapper, agreement with the stored traces is reported (WP I found its native resolver deterministic on these chains).

## Expectations stated before outcomes

- P1 raises correct endpoints and removes most wrong ones for the deployed cascade, because its errors are requested placements on copies or look-alikes only under the guards; without guards many wrong placements are silent and P1 cannot act on them.
- P2 lowers later requests under the identity rule (q0 follows the reviewed change) without raising missed-last.
