"""Build the v11 manuscript end to end and check the log.

Run: python -I -B tools/v11/make_v11.py   (from paper-drafts/, Python 3.12 for vendored matplotlib)
Steps: WP D tables -> macros -> effort figure -> floats -> reproducibility -> WP I macros/tables -> assemble ->
pdfLaTeX twice (no shell escape) -> check_v11_log. Exits non-zero on any failure.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = [sys.executable, "-I", "-B"]
STEPS = ["build_wpd_tex.py", "build_wpc_v11_tex.py","build_v11_numbers.py", "build_effort_figure.py", "build_floats.py",
         "build_repro_tex.py", "build_wpi_tex.py", "build_wpj_tex.py", "build_wpk_all.py", "assemble_v11.py"]


def run(cmd: list[str], cwd: Path) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stdout.write(r.stdout[-3000:] + r.stderr[-3000:])
        raise SystemExit(f"failed: {' '.join(cmd)}")
    last = (r.stdout.strip().splitlines() or [""])[-1]
    print(f"ok  {Path(cmd[-1]).name if cmd[0] != 'pdflatex' else 'pdflatex'}  {last[:120]}")


def main() -> None:
    for step in STEPS:
        run(PY + [str(ROOT / "tools/v11" / step)], ROOT)
    tex = ROOT / "v11-professor-revision"
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "paper-v11.tex"],
                           cwd=tex, capture_output=True, text=True, encoding="latin-1")
    check = subprocess.run(PY + [str(ROOT / "tools/v11/check_v11_log.py")], cwd=ROOT, capture_output=True, text=True)
    print(check.stdout[-4000:])
    pdf = tex / "paper-v11.pdf"
    print("pdf sha256", hashlib.sha256(pdf.read_bytes()).hexdigest())
    sys.exit(check.returncode)


if __name__ == "__main__":
    main()
