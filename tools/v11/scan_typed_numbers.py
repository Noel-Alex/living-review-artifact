"""List digits typed directly into the v11 section prose (outside macros, labels and comments).

Run: python -I -B tools/v11/scan_typed_numbers.py
Each hit must be a definition, parameter or citation-level fact rather than a result; results
must come from generated macros. Output is reviewed by hand and recorded in V11-WPG2-CLAIMS.md.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"new-bibitems.tex"}


def main() -> None:
    for f in sorted((ROOT / "v11-professor-revision/sections").glob("*.tex")):
        if f.name in SKIP:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = re.sub(r"(?<!\\)%.*", "", line)
            s = re.sub(r"\\(ref|label|cite|eqref|input|includegraphics|url|path|texttt)\{[^}]*\}", "", s)
            s = re.sub(r"\\[A-Za-z]+", "", s)
            for mt in re.finditer(r"[0-9][0-9.,]*", s):
                ctx = s[max(0, mt.start() - 40):mt.end() + 25].replace("\n", " ")
                print(f"{f.name}:{i}: {mt.group()}  | {ctx}")


if __name__ == "__main__":
    main()
