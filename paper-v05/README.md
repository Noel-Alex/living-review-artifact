# Preserving Code Review Comments Across Revisions (v05)

Raisa Jose, Noel Alex Samuel, Khadheeja Safar and Kalyanaraman P, School of Computer Science and
Engineering, Vellore Institute of Technology, Vellore.

| File | What it is |
|---|---|
| [`main.pdf`](main.pdf) | The manuscript, 15 pages, IEEE two-column. |
| [`main.tex`](main.tex) | Its complete LaTeX source. All twelve tables are LaTeX. |
| [`assets/`](assets/) | The two diagrams (Fig. 1 and Fig. 2; each caption is part of its image). |
| [`retained-inputs.json`](retained-inputs.json) | Every population the paper reports, mapped to the files in this repository that hold its numbers, with SHA-256 digests. |

The same files, ready to upload to Overleaf, are attached to the
[`v05` release](https://github.com/Noel-Alex/living-review-artifact/releases/tag/v05) as `paper-v05-latex.zip`.

## Compile

Overleaf: upload the zip, keep the default pdfLaTeX compiler, and compile. XeLaTeX also works; it uses
Tinos when installed and TeX Gyre Termes otherwise.

Locally, run twice:

    pdflatex main.tex
    pdflatex main.tex

## Where the numbers come from

This edition reports public data and author-derived constructed suites only. The four private project
histories and the twenty student repositories used by earlier editions are excluded, as is every total
that pooled them with public data.

| Paper | Source in this repository |
|---|---|
| Section I, review-thread statistic | `v12-ieee15/generated/numbers-v11.tex` (`wpe*` macros) |
| Table VI, public Python histories | `v12-ieee15/generated/numbers-v11.tex` (`smPubTgt*`, `smPubUni*` macros) |
| Table VII, human-annotated benchmark | `v12-ieee15/generated/table-external.tex` |
| Table VIII, guard stress tests | `v12-ieee15/generated/table-stress.tex` |
| Table IX, safety-layer outcomes | `v12-ieee15/generated/table-locator.tex` (human-annotated and constructed-stress columns only) |
| Table X, suggestion oracle | `v12-ieee15/generated/table-suggestion.tex` |
| Table XI, copy suite | `v12-ieee15/generated/table-copysuite.tex` |
| Table XII, state contract | `v12-ieee15/generated/table-contract.tex` |

`retained-inputs.json` lists the evidence files and builders behind each one.
`python -I -B tools/release/verify_artifact.py` rebuilds all of these macro and table files from the
shipped evidence and checks them byte for byte.
