"""Build the 15-page IEEE version (v12) from the v11 evidence build.

Run: tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v12/make_v12.py [--rebuild-v11]

The v12 text lives in v12-ieee15/sections-v12/*.tex (concatenated in name order). Every number comes from
the v11 build: the preamble macros of v11-professor-revision/paper-v11.tex, its generated/ macro files,
tables and figures, which are copied (never edited) into v12-ieee15/. Bibliography entries are taken from
paper-v11.tex, keeping only cited keys in order of first citation. Exits non-zero on any LaTeX error,
undefined reference or citation, or overfull box wider than 1pt.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V11 = ROOT / "v11-professor-revision"
V12 = ROOT / "v12-ieee15"
PY = [sys.executable, "-I", "-B"]
FLOATS = ("tab:related", "fig:cascade", "tab:labels", "fig:states", "fig:deploy", "tab:metrics", "tab:safety")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if "--rebuild-v11" in sys.argv:
        r = subprocess.run(PY + [str(ROOT / "tools/v11/make_v11.py")], cwd=ROOT)
        if r.returncode:
            print("v11 build failed")
            return 1
    src = (V11 / "paper-v11.tex").read_text(encoding="utf-8")
    cut = src.index("\\input{sections/abstract-conclusion}")
    preamble = re.sub(r"\A(?:%[^\n]*\n)+", "", src[:cut])  # drop v11's own build-comment header
    b0 = src.index("\\begin{thebibliography}")
    b1 = src.index("\\end{thebibliography}")
    bib = src[src.index("\n", b0) + 1:b1]
    bibhead = bib[:bib.index("\\bibitem{")]  # IEEEtran helper definitions that precede the first entry
    items = {}
    for m in re.finditer(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem\{|\Z)", bib, re.S):
        items[m.group(1)] = m.group(2).strip()

    for sub in ("generated", "figures"):
        (V12 / sub).mkdir(parents=True, exist_ok=True)
        for f in sorted((V11 / sub).iterdir()):
            if f.is_file():
                shutil.copy2(f, V12 / sub / f.name)
    shutil.copy2(V11 / "sections/abstract-conclusion.tex", V12 / "generated/v11-abstract-conclusion.tex")
    # Hand-written v11 floats reused verbatim: extracted by label so they cannot drift from v11.
    for label in FLOATS:
        i = src.index("\\label{%s}" % label)
        starts = [m for m in re.finditer(r"\\begin\{(table\*?|figure\*?)\}", src[:i])]
        m = starts[-1]
        env = m.group(1)
        j = src.index("\\end{%s}" % env, i) + len("\\end{%s}" % env)
        name = "v11float-" + label.replace(":", "-") + ".tex"
        (V12 / "generated" / name).write_text(
            "% Extracted from v11 paper-v11.tex by tools/v12/make_v12.py; do not edit.\n" + src[m.start():j] + "\n",
            encoding="utf-8")

    parts = sorted((V12 / "sections-v12").glob("*.tex"))
    body = "\n".join(p.read_text(encoding="utf-8") for p in parts)
    scan = re.sub(r"\\input\{(generated/[^}]+)\}",
                  lambda m: (V12 / (m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex")).read_text(encoding="utf-8"),
                  body)
    if "\\vAcknowledgment" in body:  # the acknowledgment macro carries its own citation
        ack = (V12 / "generated/v11-abstract-conclusion.tex").read_text(encoding="utf-8")
        scan += ack[ack.index("\\newcommand{\\vAcknowledgment}"):]
    order = []
    for m in re.finditer(r"\\cite\{([^}]+)\}", re.sub(r"(?<!\\)%.*", "", scan)):
        for k in m.group(1).split(","):
            k = k.strip()
            if k not in order:
                order.append(k)
    missing = [k for k in order if k not in items]
    if missing:
        print("citations without v11 bibitems:", missing)
        return 1
    bibtex = "\\begin{thebibliography}{%d}\n" % len(order) + bibhead + "\n\n".join(
        f"\\bibitem{{{k}}}\n{items[k]}" for k in order) + "\n\\end{thebibliography}\n"
    head = ("% Living Review, 15-page IEEE version (v12). Assembled by tools/v12/make_v12.py; do not edit.\n"
            "% Text: v12-ieee15/sections-v12/*.tex. Numbers, tables and figures: the v11 evidence build.\n")
    tex = head + preamble + "\\input{generated/v11-abstract-conclusion}\n" + body + "\n" + bibtex + "\n\\end{document}\n"
    out = V12 / "paper-v12.tex"
    out.write_text(tex, encoding="utf-8")

    for i in range(3):
        r = subprocess.run(["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", out.name],
                           cwd=V12, capture_output=True, text=True, encoding="latin-1")
    check = subprocess.run(PY + [str(ROOT / "tools/v11/check_v11_log.py"), str(V12 / "paper-v12.log")],
                           cwd=ROOT, capture_output=True, text=True)
    print(check.stdout)
    # A macro whose backslash was lost prints its own name; fail on any such leak in the rendered text.
    txt = subprocess.run(["pdftotext", str(V12 / "paper-v12.pdf"), "-"], capture_output=True, text=True,
                         encoding="latin-1").stdout
    leaks = sorted(set(re.findall(r"\b(?:wi|wj|sm|wpd|wpa|wpe|cExt|hTwo|bTwo|refdir|theta)[A-Z][A-Za-z]{3,}\b", txt)))
    if leaks:
        print("macro names leaked into the PDF text:", leaks)
        return 1
    words = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[A-Za-z]+", " ", body)))
    prov = {"v11_tex_sha256": sha(V11 / "paper-v11.tex"), "sections": {p.name: sha(p) for p in parts},
            "cited": len(order), "body_words_approx": words,
            "pdf_sha256": sha(V12 / "paper-v12.pdf") if (V12 / "paper-v12.pdf").exists() else None}
    (V12 / "generated/v12-provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print("cited", len(order), "of", len(items), "| body words ~", words, "| pdf", prov["pdf_sha256"])
    return check.returncode


if __name__ == "__main__":
    sys.exit(main())
