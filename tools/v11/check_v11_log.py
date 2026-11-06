"""Summarize a pdfLaTeX log: errors, undefined references/citations, overfull boxes > 1pt, pages.

Run: python -I -B tools/v11/check_v11_log.py [v11-professor-revision/paper-v11.log]
Exit status 0 only when there are no errors, no undefined references or citations, and no
overfull box wider than 1pt.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "v11-professor-revision/paper-v11.log"
    text = log.read_text(encoding="latin-1")
    errors = re.findall(r"^! .*$(?:\n.*){0,2}", text, re.M)
    undef = sorted(set(re.findall(r"(Reference|Citation) `([^']+)' on page", text)))
    over = [(float(w), ctx.strip()) for w, ctx in re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\) (.*)", text)]
    over = [o for o in over if o[0] > 1.0]
    pages = re.search(r"Output written on .*\((\d+) pages", text)
    rerun = "Rerun to get" in text or "Label(s) may have changed" in text
    out = {"errors": errors[:20], "undefined": [f"{a}:{b}" for a, b in undef], "overfull_gt_1pt": over,
           "pages": int(pages.group(1)) if pages else None, "rerun_needed": rerun}
    print(json.dumps(out, indent=1))
    return 0 if not errors and not undef and not over else 1


if __name__ == "__main__":
    sys.exit(main())
