"""Count abstract words with every macro expanded from the generated numbers file.

Run: python -I -B tools/v11/abstract_words.py   (from paper-drafts/)
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V11 = ROOT / "v11-professor-revision"


def main() -> None:
    nums = {}
    for name in ("numbers-v11.tex", "numbers-wpi.tex"):
        nums.update(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", (V11 / "generated" / name).read_text(encoding="utf-8")))
    nums["sys"] = "Living Review"
    src = (V11 / "sections/abstract-conclusion.tex").read_text(encoding="utf-8")
    body = src[src.index("\\newcommand{\\vAbstract}{%") + len("\\newcommand{\\vAbstract}{%"):src.index("\\newcommand{\\vConclusion}")]
    body = body.strip().rstrip("}")
    text = re.sub(r"\\([A-Za-z]+)(\{\})?", lambda mt: nums.get(mt.group(1), ""), body).replace("\\%", "%")
    words = re.findall(r"\S+", text)
    print(len(words))
    print(text)


if __name__ == "__main__":
    main()
