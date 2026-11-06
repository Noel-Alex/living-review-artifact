"""List every sentence with a number or numeric macro in the abstract, introduction,
discussion and conclusion of paper-v11.tex, with each macro's generated value and
its source input. Writes review/v11-wpg2-claims.json; V11-WPG2-CLAIMS.md is written from it.

Run: python -I -B tools/v11/claim_audit.py   (from paper-drafts/)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V11 = ROOT / "v11-professor-revision"
NUMS = V11 / "generated/numbers-v11.tex"


def macros() -> dict[str, str]:
    return dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", NUMS.read_text(encoding="utf-8")))


def between(text: str, a: str, b: str) -> str:
    i = text.index(a)
    return text[i:text.index(b, i)]


def sentences(block: str) -> list[str]:
    block = re.sub(r"(?<!\\)%.*", "", block)
    block = re.sub(r"\s+", " ", block)
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z\\])", block) if s.strip()]


def main() -> None:
    nums = macros()
    paper = (V11 / "paper-v11.tex").read_text(encoding="utf-8")
    ac = (V11 / "sections/abstract-conclusion.tex").read_text(encoding="utf-8")
    parts = {
        "abstract": between(ac, "\\newcommand{\\vAbstract}", "\\newcommand{\\vConclusion}"),
        "introduction": between(paper, "\\section{Introduction}", "\\section{Background"),
        "discussion": between(paper, "\\section{Discussion}", "\\section{Conclusion}"),
        "conclusion": between(ac, "\\newcommand{\\vConclusion}", "\\newcommand{\\vAcknowledgment}"),
    }
    out = []
    for part, block in parts.items():
        for s in sentences(block):
            used = [m for m in re.findall(r"\\([A-Za-z]+)", s) if m in nums]
            plain = re.sub(r"\\(ref|eqref|label|cite)\{[^}]*\}", "", s)
            plain = re.sub(r"\\[A-Za-z]+", "", plain)
            typed = re.findall(r"(?<![A-Za-z])\d[\d,.]*", plain)
            refs = re.findall(r"\\ref\{([^}]*)\}", s)
            if used or typed:
                out.append({"part": part, "sentence": s[:400], "macros": {m: nums[m] for m in used},
                            "typed": typed, "refs": refs})
    (ROOT / "review/v11-wpg2-claims.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in out:
        print(r["part"], "|", r["macros"], "| typed:", r["typed"], "| refs:", r["refs"])
        print("   ", r["sentence"][:220])


if __name__ == "__main__":
    main()
