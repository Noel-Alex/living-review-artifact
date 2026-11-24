# Preserving Code Review Comments Across Revisions: artifact

Manuscript, LaTeX source, cited papers, code, evidence and generated numbers for *Preserving Code Review
Comments Across Revisions* (Raisa Jose, Noel Alex Samuel, Khadheeja Safar and Kalyanaraman P, School of
Computer Science and Engineering, VIT Vellore). The system it evaluates is called Living Review.

The current edition is **v05**, tagged as release
[`v05`](https://github.com/Noel-Alex/living-review-artifact/releases/tag/v05).

## Contents

| Path | What it is |
|---|---|
| [`paper-v05/`](paper-v05/) | **The manuscript** ([`main.pdf`](paper-v05/main.pdf), 15 pages), its LaTeX source, and the retained-input manifest that maps every reported population to its evidence here. The release attaches the LaTeX as an Overleaf-ready zip. |
| [`references/`](references/) | The 41 cited works in citation order with DOIs, and PDFs of 35 of them. |
| `evidence/` | Every evidence file the build reads, except the private inputs listed below. Each JSON records the SHA-256 of the code and inputs that produced it. |
| `tools/v11/`, `tools/v12/` | Runners, analyses and builders. |
| `review/` | The frozen protocols, recorded before the analyses they govern ran. |
| `v12-ieee15/` | The previous 16-page edition and its source. `v12-ieee15/generated/` holds every macro file and generated table; v05 takes its numbers from there. |
| `v11-professor-revision/` | The extended technical report (66 pages) and its LaTeX source. |
| `tools/release/verify_artifact.py` | Checks `SHA256SUMS` and rebuilds the macro and table files from the shipped evidence. |

v05 is the public-data edition. It reports only the five public Python histories, the CodeMapper human-annotated
benchmark, the applied GitHub review suggestions and the author-derived constructed suites. The private project
histories and selected student repositories that the earlier editions also used do not contribute to any v05
result.

## Verify

    python -I -B tools/release/verify_artifact.py

The script checks every file against `SHA256SUMS`, then reruns the macro builders in a temporary copy and
compares their output with the shipped macro and table files. It needs Python 3.12 or later and NumPy.
Expected differences are listed by the script: one macro (`wiStuTrRenamed`) needs the private student rows,
the reproducibility section hashes the private selection manifest, and the state-specification tables are
built from portal source text that is shipped only as digests. None of these is used by v05.

## Not included

- Six of the cited papers, which have no open copy; [`references/README.md`](references/README.md) lists their DOIs.
- The 20 student-authored repositories' identities and rows. They are public GitHub repositories, but they are
  student work and are pseudonymized in the earlier editions.
- The four internal project histories, including the review portal's source. The portal state analysis
  (`evidence/v11-wpd/*.json`) quotes portal source, file inventories and test identifiers, so each of those
  files ships as a stub with its SHA-256 and size; its generated tables (`evidence/v11-wpd/tex/`) ship. In the
  bounded-model record (`evidence/v12-wpk4/`) every quoted source line is replaced by its SHA-256 and length.
  The generator of the state analysis (`tools/v11/wpd_state.py`) embeds portal source and is not shipped.
- The controlled-edit corpus, bare clones of the public histories (re-fetch them at the pinned heads), raw
  model transcripts and the suggestion-oracle file blobs (re-fetchable by commit and path). The sampled
  old/new code windows that the models saw do ship (`evidence/v12-wpk6/llm/sample.json`).
- The ReviewAnchorBench package and its third-party source files. The package is on Zenodo
  (doi 10.5281/zenodo.22217751); `tools/v12/rab_fetch.py` re-fetches the sources from the pinned URLs in its
  manifest and checks their hashes, and `tools/v12/rab_cases.py` rebuilds the cases.
- Third-party identity fields (commit author and committer) in the pinned CodeMapper commit record.
- The blinded 120-item human-annotation packet and its key. They sample internal and student code.

## Licence

Code: MIT. Our evidence, tables and text: CC BY 4.0. The cited papers in `references/pdf/` are not ours;
each keeps its publisher's or authors' copyright and licence. The review-suggestion records in
`evidence/v12-wpk6/` quote code and comments from ten public repositories, each under MIT or Apache-2.0
(SPDX identifiers in `evidence/v12-wpk6/selection.json`); that material keeps its own licence and
attribution. The case identifiers, repository names, paths, ranges and source URLs in `evidence/v12-wpk7/`
(units.json, rows.json, fetch-report.json) come from ReviewAnchorBench (J. Fu, CC BY 4.0,
doi 10.5281/zenodo.22217751).
