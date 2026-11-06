"""Assemble the v11 manuscript (paper-v11.tex) from the v10 base, v11 sections and generated files.

Run: python -I -B tools/v11/assemble_v11.py   (from paper-drafts/)
v10 text is sliced by heading markers, then corrected by exact-match edits that must each apply
once (the script fails otherwise). Every edit is logged to review/V11-WPG2-EDITS.json for the
changes record. The bibliography is reordered by first citation; uncited entries are reported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V11 = ROOT / "v11-professor-revision"
MAIN = (V11 / "main.tex").read_text(encoding="utf-8")
LOG: list[dict[str, str]] = []


def cut(start: str, end: str | None, text: str = MAIN) -> str:
    """Text from the line beginning with `start` up to the line beginning with `end`."""
    i = text.index(start)
    j = text.index(end, i + len(start)) if end else len(text)
    return text[i:j]


def edit(text: str, old: str, new: str, why: str) -> str:
    n = text.count(old)
    assert n == 1, f"{n} matches for edit: {why}: {old[:80]!r}"
    LOG.append({"why": why, "old": old, "new": new})
    return text.replace(old, new)


def drop(text: str, start: str, end: str, why: str) -> str:
    """Remove from `start` through the end of the first following `end`."""
    return edit(text, cut(start, end, text) + end, "", why)


def sec(name: str) -> str:
    return (V11 / "sections" / name).read_text(encoding="utf-8")


def gen(name: str) -> str:
    return f"\\input{{generated/{name}}}\n"


# ---------- preamble, title, abstract, introduction ----------
pre = cut(MAIN[:1], "\\begin{document}")
pre = edit(pre, "% Build: pdflatex main.tex twice with shell escape disabled.",
           "% Build: pdflatex paper-v11.tex twice with shell escape disabled (assembled by tools/v11/assemble_v11.py).",
           "build note names the assembled file")
pre += ("% v11: a note with an empty table argument spans the float instead of a zero-width box.\n"
        "\\renewcommand{\\tablenote}[2]{\\sbox{\\tabbox}{#1}\\ifdim\\wd\\tabbox=0pt\\par\\smallskip"
        "\\parbox{\\linewidth}{\\footnotesize #2}\\else\\usebox{\\tabbox}\\par\\vspace{3pt}"
        "\\parbox{\\wd\\tabbox}{\\footnotesize #2}\\fi}\n"
        "\\input{generated/numbers-v11}\n\\input{generated/numbers-wpi}\n\\input{generated/numbers-wpj}\n\\input{generated/numbers-wpk}\n\\input{sections/abstract-conclusion}\n")
title = cut("\\begin{document}", "\\begin{abstract}")
keywords = cut("\\begin{IEEEkeywords}", "\\section{Introduction}")
keywords = edit(keywords, "software evolution, educational software", "software evolution, language models",
                "R03 minor 21: educational effects were not measured")
intro = cut("\\section{Introduction}", "\\section{Background and Related Work}")
intro = edit(intro, "external human-annotated data (Sections~\\ref{sec:method}--\\ref{sec:real})",
             "external human-annotated data (Sections~\\ref{sec:method}--\\ref{sec:stress})",
             "contribution (3) spans the evaluation sections through RQ4")
intro = edit(intro, "\\textbf{RQ5} (state contract): does the implemented issue lifecycle match its specification, in particular that no system action resolves an issue?",
             "\\textbf{RQ5} (locator transfer): does the safety-oriented workflow improve the reliability of an already strong locator, and does keeping the reviewed quotation make identity transitions across many versions visible? \\textbf{RQ6} (state contract): does the implemented issue lifecycle match its specification, in particular that no system action resolves an issue?",
             "R02: stronger locator inside the workflow becomes RQ5")
intro = edit(intro, "with three guards derived from its failure analysis.",
             "with three guards derived from its failure analysis, and evidence that the locator-independent part of this layer (the change labels, the indentation and copy guards and the issue-state policy), placed over the stronger locator CodeMapper, makes it safer without changing its placement (Section~\\ref{sec:locator}).",
             "R02: locator-agnostic safety layer in contribution (1)")
intro = edit(intro, "specified as a transition relation and checked against its implementation (Sections~\\ref{sec:design}--\\ref{sec:impl}).",
             "specified as a transition relation and checked against its implementation (Sections~\\ref{sec:design}--\\ref{sec:impl}), with an identity rule that keeps the reviewed quotation across versions (Section~\\ref{sec:identity}).",
             "R02: identity rule in contribution (2)")

# ---------- III Design ----------
design = cut("\\section{Design}", "\\subsection{Relocation}")
design = edit(design, r"\node[lbl, fill=ink, text=white, right=5mm of t1] (l1) {exact};",
              r"\node[lbl, fill=ink, text=white, right=5mm of t1] (l1) {identical};", "five-label vocabulary (Fig. 1, tier 1)")
design = edit(design, r"\node[lbl, fill=ink, text=white, right=5mm of t2, yshift=2.5mm] (l2a) {exact};",
              r"\node[lbl, fill=ink, text=white, right=5mm of t2, yshift=2.5mm] (l2a) {content-match};",
              "five-label vocabulary (Fig. 1, tier 2 at the old start)")
design = edit(design, r"\Return $(\pi, s, e, \lbl{exact})$", r"\Return $(\pi, s, e, \lbl{identical})$",
              "five-label vocabulary (Algorithm 1, tier 1)")
design = edit(design, r"s' = s\ ?\ \lbl{exact} : \lbl{moved}", r"s' = s\ ?\ \lbl{content-match} : \lbl{moved}",
              "five-label vocabulary (Algorithm 1, tier 2)")
states = cut("\\subsection{State Invariant and Matching Limits}", "% System architecture section")
states = states[states.index("\\begin{figure}[t]"):]  # v10 invariant paragraph superseded by design-relocation.tex
states = edit(states, r"{carried; all anchors\ \lab{exact} or \lab{moved}}",
              r"{carried; all anchors\ \lab{identical},\\ \lab{content-match} or \lab{moved}}", "five-label vocabulary (Fig. 2)")
states = edit(states, "A finding raised again is matched to a carried issue by category, title and overlapping evidence, so that a carried concern is not duplicated.",
              "A finding raised again is matched to a carried issue by category, title and overlapping evidence, so that a carried concern is not duplicated; the carried issue takes the fresh evidence, an active one returns for re-check, and a resolved or dismissed one keeps its state.",
              "WP D: re-raised finding semantics")
states = edit(states, "Fig.~\\ref{fig:states} summarizes the lifecycle.",
              "Fig.~\\ref{fig:states} summarizes the lifecycle and Table~\\ref{tab:transitions} specifies it.",
              "point to the WP D transition table")

# ---------- IV Architecture ----------
arch = cut("% System architecture section", "\\subsection{Integrity Properties}")
arch = edit(arch, "An optional assistant runs as its own service and can create, edit and delete review points through journaled, undoable tool calls, but cannot publish, and a resolve or dismiss it suggests takes effect only when a supervisor applies it.",
            "An optional assistant runs as its own service and edits review points only through journaled, undoable tool calls (Section~\\ref{sec:statecheck}).",
            "brief: assistant sentence in Deployment shortened to one clause")

# ---------- V Method ----------
method = cut("\\section{Evaluation Method}", "\\section{Controlled Edit Results}")
method = edit(method, "The code is real, maintained application code, not generated text.",
              "The code is real, maintained application code, not generated text. Real-history projects are described in Section~\\ref{sec:real}; the human-annotated external benchmark and the student-authored repositories in Section~\\ref{sec:external}.",
              "brief: add external and student corpora to Corpus")
method = edit(method, "The original LHDiff binary and GumTree are not benchmarked. A separately pinned third-party hybrid tracker",
              "The original LHDiff binary is not available to us. GumTree's official release and the pinned CodeMapper artifact \\cite{hu2026codemapper} are evaluated on the external benchmark (Section~\\ref{sec:external}). A separately pinned third-party hybrid tracker",
              "brief: GumTree and CodeMapper added to Baselines (v10 said GumTree was not benchmarked)")
method = edit(method, "for the cascade this corresponds to an erroneous \\lbl{exact} label. A \\lbl{moved} label can still fail to trigger re-check. We therefore report the exact-label count alongside re-check recall and a second reference definition.",
              "for the cascade this corresponds to an erroneous \\lbl{content-match} label (deployed identifier \\texttt{exact}). A \\lbl{moved} label can still fail to trigger re-check, so Section~\\ref{sec:safety} reports missed re-checks and silent misplacements as separate rates.",
              "five-label vocabulary; point to the safety metrics")
method += sec("method-additions.tex")

# ---------- VI RQ1 controlled ----------
ctl = cut("\\section{Controlled Edit Results}", "\\subsection{RQ2: Labels and Re-checks}")
ctl += cut("\\subsection{RQ3: Combined Design}", "\\section{Real-History Evaluation}")
ctl = edit(ctl, "\\section{Controlled Edit Results}", "\\section{RQ1: Location on Controlled Edits}", "brief: RQ section titles")
ctl = edit(ctl, "\\subsection{RQ1: Start-Location Accuracy}", "\\subsection{Start-Location Accuracy}", "brief: RQ section titles")
ctl = edit(ctl, "\\subsection{RQ3: Combined Design}", "\\subsection{Combined Design on Controlled Edits}", "brief: RQ section titles")
ctl = edit(ctl, "\\subsection{RQ4: Robustness and Cost}", "\\subsection{Anchor Height, File Length and Cost}", "brief: RQ section titles")
ctl = edit(ctl, "\\subsection{RQ1: Independent Hybrid Tracker}", "\\subsection{Independent Hybrid Tracker}", "brief: RQ section titles")
ctl = edit(ctl, "an erroneous moved label can still miss workflow re-check (Section~\\ref{sec:results}, RQ2).",
           "an erroneous moved label can still miss workflow re-check (Section~\\ref{sec:safety}).", "v10 RQ2 subsection removed")
ctl = edit(ctl, "These comparisons do not separate window scope from tier order.",
           "These comparisons do not separate window scope from tier order; the factorial analysis of Section~\\ref{sec:design-results} does.",
           "point to the WP A factorial")

# ---------- VII RQ1 real histories ----------
real = cut("\\section{Real-History Evaluation}", "\\subsection{RQ2: Re-checks on Real Edits}")
real = drop(real, "\\begin{figure}[t]\n\\centering\n\\includegraphics[width=\\columnwidth]{figures/real-labels-v1.pdf}",
            "\\end{figure}\n", "label figure superseded by the safety section")
real += cut("\\subsection{Sensitivity to the Definition of Change}", "\\subsection{RQ3: Real-Edit Trade-offs}")
real += cut("\\subsection{Independent Tracker on Real Histories}", "\\subsection{RQ5: Ten Successive Revision Hops}")
real = edit(real, "\\section{Real-History Evaluation}", "\\section{RQ1: Location on Real Histories}", "brief: RQ section titles")
real = edit(real, "To test the findings on edits nobody designed (RQ5)", "To test the findings on edits nobody designed", "RQ renumbering")
real = edit(real, "Pairwise accuracy and re-checks address RQ5 and RQ2; definition sensitivity and complete-source checks explain their reference limits (Sections~\\ref{sec:definitionaudit} and~\\ref{sec:sourcecontext}). Calibration examines RQ3, followed by independent tracking, full-range recovery and ten-hop replay (Sections~\\ref{sec:realtracker}--\\ref{sec:chains}).",
            "This section reports location; definition sensitivity and complete-source checks explain the reference's limits (Sections~\\ref{sec:definitionaudit} and~\\ref{sec:sourcecontext}), followed by independent tracking and full-range recovery (Sections~\\ref{sec:realtracker} and~\\ref{sec:ranges}). Re-checks, calibration and repeated resubmission are reported in Sections~\\ref{sec:safety}--\\ref{sec:stress}.",
            "RQ renumbering and section map")
real = edit(real, "\\subsection{RQ5: Start Accuracy on Real Edits}", "\\subsection{Start Accuracy on Real Edits}", "brief: RQ section titles")
real = edit(real, "\\subsection{RQ1: Source-Line Range Recovery}", "\\subsection{Source-Line Range Recovery}", "brief: RQ section titles")
for old, new in [("Of these 2,508 reference events, 52 were labelled exact or moved", "Of these 2,508 reference events, 52 were labelled \\lbl{content-match} or \\lbl{moved}"),
                 ("Eleven replacement observations were labelled exact.", "Eleven replacement observations were labelled \\lbl{content-match}."),
                 ("(11 exact and 10 moved)", "(11 \\lbl{content-match} and 10 \\lbl{moved})"),
                 ("does not establish that no structural statement change was labelled exact.", "does not establish that no structural statement change was labelled \\lbl{content-match}."),
                 ("Reference definition & $n$ & Missed & Exact & Recall", "Reference definition & $n$ & Missed & \\shortstack[r]{Content-\\\\match} & Recall"),
                 ("Missed means labelled exact or moved, neither of which requests re-check. Exact is the number of misses labelled exact.",
                  "Missed means labelled \\lbl{content-match} or \\lbl{moved}, neither of which requests re-check. Content-match is the number of misses with that label."),
                 ("Eleven observations retain an exact label:", "Eleven observations retain a \\lbl{content-match} label:"),
                 ("The exact label is therefore compatible with identical quoted lines", "The \\lbl{content-match} label is therefore compatible with identical quoted lines")]:
    real = edit(real, old, new, "five-label vocabulary (only tier 2 can label changed code content-match)")
real = edit(real, "Thus its \\emph{edited} class is not identical to the set of changed AST statements (Section~\\ref{sec:definitionaudit}).",
              "Thus its \\emph{edited} class is not identical to the set of changed AST statements (Section~\\ref{sec:definitionaudit}).\n\n"
              "\\emph{Direction of reference error.} The reference calls a target unchanged only when the quoted lines, ignoring "
              "whitespace, stand at its location and occur once in that file; each of the \\refdirCertified{} "
              "real-history targets it called unchanged passes this check. The check shows that the text there is unchanged, not "
              "that it is the reviewed code. For \\refcopyAligned{} of these targets identity rests on an equal syntax tree at the "
              "aligned position of the same function and for \\refcopyPaired{} on same-type pairing; the other \\refcopyRelocated{} "
              "left their function and were placed on the unique equal statement elsewhere in the new version. Reading the earlier "
              "version of the public histories (tools/v11/audit\\_reference\\_copies.py), \\refcopySuspect{} of the "
              "\\refcopyChecked{} relocated targets landed where an identical statement already stood before the revision, so the "
              "reference may have taken a pre-existing copy for the reviewed code; the deployed cascade requested no check on any of "
              "them. Counted as hidden misses they raise the deployed miss rate from \\refdirMissPct\\% to "
              "\\refcopyMissPctChecked\\%, and counting also the \\refcopyUnavailable{} relocations in our own projects, whose earlier "
              "versions this check could not read, gives \\refcopyMissPctWorst\\%. In the other direction, the same-type pairing of "
              "replaced statements decides \\refdirPaired{} of the \\refdirChanged{} changed or deleted targets. Of the deployed "
              "cascade's \\wpaMissTotal{} real-history misses (Section~\\ref{sec:safety}), \\refdirMissAligned{} rest on an equal "
              "syntax tree at the aligned position, \\refdirMissPaired{} on same-type pairing and \\refdirMissDeleted{} on a "
              "deletion. Even if every pairing and deletion behind a miss were wrong, and the copy the cascade found were the true "
              "target, the miss rate would fall to \\refdirBoundPct\\%. Under these reference errors the deployed miss rate lies "
              "between \\refdirBoundPct\\% and \\refcopyMissPctWorst\\%. The bounds cover missed re-checks only: identification "
              "errors can move placement accuracy either way and can hide unnecessary re-checks. The student-authored repositories "
              "use the same reference unchanged.",
              "R03 major 7: direction of reference error (evidence/v11-wpa/reference-direction.json)")

# ---------- RQ4 stress with the v10 ten-hop replay ----------
chains = cut("\\subsection{RQ5: Ten Successive Revision Hops}", "\\section{Threats to Validity}")
chains = edit(chains, "\\subsection{RQ5: Ten Successive Revision Hops}", "\\subsection{Ten Successive Revision Hops}", "brief: ten-hop replay moved under RQ4")
for old, new in [("82 endpoint errors end with an exact last-hop label", "82 endpoint errors end with an \\lbl{identical} or \\lbl{content-match} last-hop label"),
                 ("188 errors end exact and 184", "188 errors end with such a label and 184"),
                 ("later receives exact labels.", "later receives \\lbl{content-match} labels."),
                 ("but the final local exact label cannot certify", "but the final local \\lbl{content-match} label cannot certify")]:
    chains = edit(chains, old, new, "five-label vocabulary")
stress = sec("stress.tex")
stress = edit(stress, "\\subsection{Repeated Resubmissions}\\label{sec:prefixes}", chains + "\\subsection{Repeated Resubmissions}\\label{sec:prefixes}",
              "insert v10 ten-hop replay before the prefix analysis")

# ---------- ethics (v10, updated for the student-authored repositories) ----------
ethics = cut("\\subsection{Ethics and Data Handling}", "\\subsection{Future Work}")
ethics = edit(ethics, "No student submission was used in this evaluation. The synthetic benchmark used our own project code, and the real histories came from our projects and from public open-source repositories, which were parsed and never executed.",
              "No student submission was used in this evaluation. The synthetic benchmark used our own project code; the real histories came from our projects, public open-source repositories and public student-authored repositories, all parsed and never executed. The student-authored repositories are pseudonymized here and no individual is identified.",
              "ethics updated for WP H2")

# ---------- appendices and bibliography ----------
app = cut("\\appendices", "% Balances the two columns")
app = edit(app, "Table~\\ref{tab:realtheta} gives the values plotted in Fig.~\\ref{fig:realtheta}, together with",
           "Table~\\ref{tab:realtheta} extends Table~\\ref{tab:tradeoff} to the full threshold grid, together with", "v10 threshold figure removed")
app = edit(app, "The method uses the fixed-default 0.85; gone code has only \\rGoneN{} cases. Table~\\ref{tab:realbest} compares Cascade v1 across the same thresholds (Appendix~\\ref{app:theta}).",
           "The method uses the fixed-default 0.85; gone code has only \\rGoneN{} cases. Table~\\ref{tab:realbest} compares Cascade v1 across the same thresholds.", "self-reference within the appendix")
app = edit(app, "The claim tracer contributes few anchors because its history is short.",
           "The claim tracer contributes few anchors because its history is short. Table~\\ref{tab:exclusions} splits commit pairs and anchors by revision horizon and gives the anchors the syntax-tree reference excluded in each project.\n\n" + gen("float-exclusions").strip(),
           "R01 H3/H7: pairs and anchors per horizon, exclusions per project")
# R03 minor 5: Appendix B text first, then its tables in the order the text cites them (realtheta, then realbest).
thetasec = cut("\\section{Threshold Sensitivity on Real Edits}", "\\section{Oracle Audit}", app)
head_end = thetasec.index("\n") + 1
t1 = thetasec.index("\\begin{table}[t]\n\\caption{Final Cascade and Internal Comparator Across Thresholds}")
t2 = thetasec.index("\\begin{table}[t]\n\\caption{Fuzzy-Tier Threshold on Real Edits}")
t2_end = thetasec.index("\\end{table}\n", t2) + len("\\end{table}\n")
assert head_end <= t1 < t2 < t2_end
app = edit(app, thetasec, thetasec[:head_end] + thetasec[t2_end:].strip("\n") + "\n\n" + thetasec[t2:t2_end] + "\n"
           + thetasec[t1:t2].strip("\n") + "\n\n", "R03 minor 5: Appendix B text before its tables, in citation order")
# R02 (professor review): tables of the WP K analyses, flushed on their own pages after the existing appendices.
app_r02 = ("\\clearpage\n\\section{Tables for the Second Review}\\label{app:r02}\n"
           "Tables for Section~\\ref{sec:r02}, in the order that section cites them.\n\n"
           + "".join(gen(n) for n in ("table-sixoutcome", "table-strata", "table-idfloor", "table-policy",
                                      "table-refaudit", "table-copysuite", "table-suggestion", "table-rab",
                                      "table-interventions-full", "table-contract"))
           + "\\clearpage\n")
bib = cut("\\begin{thebibliography}", "\\end{thebibliography}")
bib += "\n" + sec("new-bibitems.tex")

body = "".join([
    title, "\\begin{abstract}\n\\vAbstract\n\\end{abstract}\n\n", keywords, intro,
    sec("related.tex"), design, sec("design-relocation.tex"), states,
    arch, sec("architecture-evidence.tex"), method, ctl, real,
    sec("external.tex"), sec("student.tex"),
    gen("float-missedcases"), gen("float-effort"), sec("safety.tex"),
    gen("float-tradeoff"), gen("float-factorial"), gen("float-lopo"), sec("design-results.tex"),
    gen("float-duplicates"), stress, sec("locator.tex"), sec("statecheck.tex"), sec("revision-r02f.tex"), sec("threats-discussion.tex"), ethics,
    "\\section{Conclusion}\n\\vConclusion\n\n\\section*{Acknowledgment}\n\\vAcknowledgment\n\n",
    gen("reproducibility"), "\n", app, app_r02])

# ---------- R03 venue review: editorial fixes on the assembled text ----------
body = edit(body, "rule checks, deep review, signed claim-to-code bundles",
            "rule checks, language-model review, signed claim-to-code bundles", "R03 minor 3: 'deep review' undefined (Fig. 3)")
body = edit(body, "(rule checks, a deep review and the partner claim-to-code tracer,",
            "(rule checks, a language-model review of the submission and the partner claim-to-code tracer,",
            "R03 minor 3: 'deep review' undefined (Deployment)")
body = edit(body, "Dotted line: the reported default $\\theta = 0.85$; no dated prospective protocol is available.}",
            "Dotted line: the reported default $\\theta = 0.85$.}", "R03 minor 11: protocol caveat moved out of the Fig. 6 caption")
body = edit(body, "The default cascade uses $\\theta=0.85$; project-disjoint calibration",
            "The default cascade uses $\\theta=0.85$, which no dated prospective protocol fixed; project-disjoint calibration",
            "R03 minor 11: protocol caveat stated in the Method section")
# R03 minor 1: one spelling convention (IEEE, American) across the assembled prose.
SPELLING = {"normalised": "normalized", "Normalisation": "Normalization", "recognised": "recognized",
            "recognises": "recognizes", "recognise": "recognize", "summarises": "summarizes", "localises": "localizes",
            "localise": "localize", "authorisation": "authorization", "analyse": "analyze", "behaviours": "behaviors",
            "behaviour": "behavior", "Behaviour": "Behavior", "favours": "favors", "favour": "favor",
            "relabelled": "relabeled", "labelled": "labeled", "unsignalled": "unsignaled",
            "judgements": "judgments", "judgement": "judgment"}
for old, new in SPELLING.items():
    n = len(re.findall(rf"\b{old}\b", body))
    if n:
        body = re.sub(rf"\b{old}\b", new, body)
        LOG.append({"why": f"R03 minor 1: American spelling ({n} occurrences)", "old": old, "new": new})

# Bibliography in order of first citation.
items = re.split(r"(?=\\bibitem\{)", bib)
head, entries = items[0], items[1:]
keyed = {re.match(r"\\bibitem\{([^}]+)\}", e).group(1): e.strip() + "\n\n" for e in entries}
order: list[str] = []
scan = body
macro_text = sec("abstract-conclusion.tex")
for name in ("vAbstract", "vConclusion", "vAcknowledgment"):  # citations inside text macros count where used
    start = macro_text.index("\\newcommand{\\" + name + "}")
    nxt = macro_text.find("\\newcommand{", start + 1)
    scan = scan.replace("\\" + name + "\n", macro_text[start:nxt if nxt > 0 else None] + "\n")
for group in re.findall(r"\\cite\{([^}]+)\}", scan):
    for k in (x.strip() for x in group.split(",")):
        if k not in order:
            order.append(k)
missing = [k for k in order if k not in keyed]
uncited = [k for k in keyed if k not in order]
assert not missing, f"cited but undefined: {missing}"
bib_head = MAIN[MAIN.index("\\begin{thebibliography}"):]
bib_head = bib_head[bib_head.index("\n") + 1:bib_head.index("\\bibitem{")]  # IEEEtran.bst support macros
bibtext = ("\\begin{thebibliography}{" + str(len(order)) + "}\n" + bib_head
           + "".join(keyed[k] for k in order) + "\\end{thebibliography}\n")
# Flush the appendix floats before the references so tables do not interleave with them.
paper = pre + body + "\n" + bibtext + "\n\\end{document}\n"
(V11 / "paper-v11.tex").write_text(paper, encoding="utf-8")
(ROOT / "review" / "V11-WPG2-EDITS.json").write_text(json.dumps(
    {"edits": LOG, "bibliography_order": order, "uncited_dropped": uncited}, indent=2), encoding="utf-8")
print(f"paper-v11.tex: {len(paper.splitlines())} lines, {len(LOG)} edits, {len(order)} references, uncited dropped: {uncited}")
