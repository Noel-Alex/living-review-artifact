# Living Review: artifact

Code, evidence and generated numbers for *Living Review: Carrying Code Review Comments Safely Across
Resubmissions* (Jose, Samuel, Safar and Kalyanaraman, VIT Vellore) and its extended technical report.

## Contents

| Path | What it is |
|---|---|
| `v12-ieee15/paper-v12.pdf` | The paper (16 pages) and, beside it, its LaTeX source. |
| `v11-professor-revision/paper-v11.pdf` | The extended technical report (66 pages) and its LaTeX source. |
| `v11-professor-revision/generated/` | Every macro file and generated table the two documents use. Every number in the text is a macro defined here. |
| `evidence/` | Every evidence file the build reads, except the private inputs listed below, plus the suggestion-oracle records (`evidence/v12-wpk6/`). Each JSON records the SHA-256 of the code and inputs that produced it. |
| `tools/v11/`, `tools/v12/` | Runners, analyses and builders. `tools/v11/make_v11.py` and `tools/v12/make_v12.py` rebuild both documents. |
| `review/` | The frozen protocols, recorded before the analyses they govern ran. |
| `tools/release/verify_artifact.py` | Checks `SHA256SUMS` and rebuilds the macro files from the shipped evidence. |

## Verify

    python -I -B tools/release/verify_artifact.py

The script checks every file against `SHA256SUMS`, then reruns the macro builders in a temporary copy and
compares their output with the shipped macro files. It needs Python 3.12 and NumPy. Expected differences are
listed by the script: one macro (`wiStuTrRenamed`) needs the private student rows, the reproducibility
section hashes the private selection manifest, and the state-specification tables are built from portal
source text that is shipped only as digests.

## Not included

- The 20 student-authored repositories' identities and rows. They are public GitHub repositories, but they are
  student work and are pseudonymized in the paper.
- The four internal project histories, including the review portal's source. The portal state analysis
  (`evidence/v11-wpd/*.json`) quotes portal source, file inventories and test identifiers, so each of those
  files ships as a stub with its SHA-256 and size; its generated tables (`evidence/v11-wpd/tex/`) ship. In the
  bounded-model record (`evidence/v12-wpk4/`) every quoted source line is replaced by its SHA-256 and length.
  The generator of the state analysis (`tools/v11/wpd_state.py`) embeds portal source and is not shipped.
- The controlled-edit corpus, bare clones of the public histories (re-fetch them at the pinned heads), raw
  model transcripts and the suggestion-oracle file blobs (re-fetchable by commit and path). The sampled
  old/new code windows that the models saw do ship (`evidence/v12-wpk6/llm/sample.json`).
- Third-party identity fields (commit author and committer) in the pinned CodeMapper commit record.
- The blinded 120-item human-annotation packet and its key. They sample internal and student code.

## Licence

Code: MIT. Our evidence, tables and text: CC BY 4.0. The review-suggestion records in `evidence/v12-wpk6/`
quote code and comments from ten public repositories, each under MIT or Apache-2.0 (SPDX identifiers in
`evidence/v12-wpk6/selection.json`); that material keeps its own licence and attribution.
