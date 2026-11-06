"""Verify the Living Review artifact: file hashes, then a rebuild of the macro files from the shipped evidence.

Run from the artifact root:  python -I -B tools/release/verify_artifact.py
Needs Python 3.12 with NumPy (and Matplotlib for the float builder). Exits non-zero on any unexpected difference.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = "v11-professor-revision/generated"
STEPS = ["build_wpc_v11_tex.py", "build_v11_numbers.py", "build_floats.py", "build_wpi_tex.py",
         "build_wpj_tex.py", "build_wpk_all.py"]
# Differences that are expected because their inputs are private (see README).
EXPECTED_MISSING = {"wiStuTrRenamed"}
MACRO = re.compile(r"\\newcommand\{\\(\w+)\}\{(.*)\}$")


def check_sums() -> int:
    bad = 0
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        p = ROOT / rel
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            print(f"hash mismatch: {rel}")
            bad += 1
    print(f"hashes: {'ok' if not bad else f'{bad} mismatches'}")
    return bad


def macros(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = MACRO.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def rebuild() -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "a"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git"))
        for step in STEPS:
            r = subprocess.run([sys.executable, "-I", "-B", str(work / "tools/v11" / step)], cwd=work,
                               capture_output=True, text=True)
            print(f"{'ok ' if r.returncode == 0 else 'ERR'} {step}")
            if r.returncode:
                print(r.stderr[-1500:])
                bad += 1
        for shipped in sorted((ROOT / GEN).glob("numbers-*.tex")):
            a, b = macros(shipped), macros(work / GEN / shipped.name)
            lost = set(a) - set(b) - EXPECTED_MISSING
            changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
            if lost or changed:
                bad += 1
                print(f"DIFF {shipped.name}: {len(lost)} missing, {len(changed)} changed, e.g. {sorted(lost)[:5]} {changed[:5]}")
            else:
                print(f"same {shipped.name} ({len(a)} macros)")
        for shipped in sorted((ROOT / GEN).glob("table-*.tex")):
            rebuilt = work / GEN / shipped.name
            if rebuilt.read_bytes() != shipped.read_bytes():
                print(f"note {shipped.name}: rebuilt table differs")
    return bad


if __name__ == "__main__":
    n = check_sums() + rebuild()
    print("VERIFIED" if n == 0 else f"FAILED ({n})")
    sys.exit(1 if n else 0)
