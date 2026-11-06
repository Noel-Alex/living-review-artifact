"""Build the public Living Review artifact from paper-drafts/ (allowlist, sanitize, scan, hash).

Run from paper-drafts/:  python -I -B tools/release/build_artifact.py [OUT]
Default OUT: release/living-review-artifact. OUT is rebuilt from scratch except its .git directory.

What ships: the analysis code, every evidence file the paper build reads (traced-inputs.txt) except the two
private ones, the public suggestion-oracle records, the generated macro files and tables, the paper and the
extended report with their LaTeX sources, and the protocols. What never ships: the student-repository
selection and rows, the internal histories, portal source text, raw model logs, bare clones and keys.
The script refuses to finish if the privacy scan finds a student identifier, a secret or a private path.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "release" / "living-review-artifact"
assert OUT != ROOT and not any(OUT == ROOT / d or ROOT / d in OUT.parents for d in ("tools", "evidence", "review")), \
    "OUT must not lie inside a copied tree"

PRIVATE_INPUTS = {"evidence/v11-wph/private/selected.json", "evidence/v11-wpi/students/rows.json"}
# Portal evidence (the portal is one of the private internal histories). Every top-level JSON of the WP D
# state analysis quotes portal source, paths or test identifiers and is read only by build_wpd_tex.py, whose
# generated tables ship; these files ship as {withheld, sha256, bytes} stubs. Elsewhere, every string under a
# "source" key is digested (all lengths), and third-party identity objects are dropped.
WITHHOLD_GLOB = "evidence/v11-wpd/*.json"
DEEP_DIGEST = {"evidence/v12-wpk4/model-check-20261105T223148Z.json": {"source"}}
DROP_KEYS = {"evidence/v11-wpc/codemapper-head.json": {"author", "committer"}}
# Tools that embed portal source as literals, and tools with absolute local paths, are not shipped.
EXCLUDE_TOOLS = {"tools/v11/wpd_state.py", "tools/v11/verify_wpa.py", "tools/v11/verify_wpb_tex.py",
                 "tools/v11/verify_wpc_tex.py"}
PORTAL_SOURCES = ["evidence/v11-wpd/state-spec.json", "evidence/v11-wpd/claims-d5.json",
                  "evidence/v11-wpd/status-writer-scan.json", "evidence/v11-wpd/model-check.json",
                  "evidence/v12-wpk4/model-check-20261105T223148Z.json"]
LOCAL_PATH = re.compile(r"(?i)\b[A-Z]:[\\/]+(users|projects)[\\/]")
EXTRA_FILES = [
    "evidence/public-histories/manifest.json",
    "evidence/v12-wpk6/rows.json", "evidence/v12-wpk6/units.json", "evidence/v12-wpk6/selection.json",
    "evidence/v12-wpk6/exclusions.json", "evidence/v12-wpk6/protocol-freeze.json",
    "evidence/v12-wpk6/protocol-amendment-1.json", "evidence/v12-wpk6/protocol-amendment-2.json",
    "evidence/v12-wpk6/llm/summary.json", "evidence/v12-wpk6/llm/sample.json",
    "evidence/v12-wpk5/protocol-freeze.json", "evidence/v12-wpk5/protocol-amendment-1.json",
    "v12-ieee15/paper-v12.pdf", "v12-ieee15/paper-v12.tex",
    "v11-professor-revision/paper-v11.pdf", "v11-professor-revision/paper-v11.tex", "v11-professor-revision/main.tex",
]
EXTRA_GLOBS = [
    "tools/v11/*.py", "tools/v11/*.java", "tools/v11/frozen/*.py", "tools/v12/*.py", "tools/release/*.py",
    "tools/release/traced-inputs.txt",
    "evidence/v11-wpd/tex/*", "evidence/v11-wpc/tex-v11/*",  # builder outputs read by later builders
    "v11-professor-revision/generated/*", "v11-professor-revision/sections/*.tex", "v11-professor-revision/figures/*",
    "v12-ieee15/generated/*", "v12-ieee15/sections-v12/*.tex", "v12-ieee15/figures/*",
    "review/V11-PROTOCOL-*.md", "review/V11-WPA-PROTOCOL.md", "review/V12-PROTOCOL-*.md",
]
SKIP_NAMES = re.compile(r"\.(aux|log|out|err|pyc)$|__pycache__")

SECRET = re.compile(r"(sk-[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|"
                    r"AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._-]{20,}|api[_-]?key\s*[=:]\s*['\"][^'\"]{12,})", re.I)
PRIVATE_PATH = re.compile(r"(wph/private|wpk6/private|wpk5/private|students/rows\.json|human-packet-key)")


def dig(v: str) -> dict:
    return {"sha256": hashlib.sha256(v.encode()).hexdigest(), "chars": len(v)}


def deep_digest(x, keys, inside=False):
    """Digest every string at or below a key in `keys`, whatever its length."""
    if isinstance(x, dict):
        return {k: deep_digest(v, keys, inside or k in keys) for k, v in x.items()}
    if isinstance(x, list):
        return [deep_digest(v, keys, inside) for v in x]
    return dig(x) if inside and isinstance(x, str) else x


def drop_keys(x, keys):
    if isinstance(x, dict):
        return {k: drop_keys(v, keys) for k, v in x.items() if k not in keys}
    if isinstance(x, list):
        return [drop_keys(v, keys) for v in x]
    return x


def portal_needles() -> set[str]:
    """Every portal source string quoted by the WP D evidence (strings under source/text/code keys)."""
    out: set[str] = set()
    def walk(x, inside=False):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, inside or k in ("source", "text", "code"))
        elif isinstance(x, list):
            for v in x:
                walk(v, inside)
        elif inside and isinstance(x, str):
            s = x.strip()
            # Skip digests and bare file paths (provenance fields), keep source text.
            if len(s) >= 15 and not re.fullmatch(r"[0-9a-f]{64}", s) and not re.fullmatch(r"[\w./-]+\.\w+", s):
                out.add(s)
    for rel in PORTAL_SOURCES:
        walk(json.loads((ROOT / rel).read_text(encoding="utf-8")))
    # A constant the paper itself states (the carry size limit, Section VIII).
    out.discard("MAX_FILE_BYTES = 400_000")
    return out


def shipped(out: Path) -> list[Path]:
    return sorted(p for p in out.rglob("*") if p.is_file() and ".git" not in p.relative_to(out).parts)


def clear(out: Path) -> None:
    """Empty OUT but keep its .git directory, so the published repository's history survives a rebuild."""
    out.mkdir(parents=True, exist_ok=True)
    for c in out.iterdir():
        if c.name != ".git":
            shutil.rmtree(c) if c.is_dir() else c.unlink()


def student_tokens() -> set[str]:
    sel = json.loads((ROOT / "evidence/v11-wph/private/selected.json").read_text(encoding="utf-8"))
    toks = set()
    for r in sel:
        owner, name = r["full_name"].split("/", 1)
        toks |= {owner.lower(), name.lower(), r["full_name"].lower(), r["head_commit_sha"][:12].lower()}
    # Tokens that are also ordinary phrases of the paper's own text, checked by hand on 2026-11-06.
    # Stored as SHA-256 so the shipped builder names no token.
    generic = {"a89bec3b8765cbb2e0d8cdb36253a0b0cbdd704f8de102b75f75ca1a30a07291"}
    return {t for t in toks if len(t) >= 5 and hashlib.sha256(t.encode()).hexdigest() not in generic}


def main() -> None:
    files: set[str] = set()
    for line in (ROOT / "tools/release/traced-inputs.txt").read_text(encoding="utf-8").split():
        if line not in PRIVATE_INPUTS:
            files.add(line)
    files |= set(EXTRA_FILES)
    for g in EXTRA_GLOBS:
        files |= {p.relative_to(ROOT).as_posix() for p in ROOT.glob(g) if p.is_file()}
    files = {f for f in files if not SKIP_NAMES.search(f) and f not in EXCLUDE_TOOLS}
    withheld = {p.relative_to(ROOT).as_posix() for p in ROOT.glob(WITHHOLD_GLOB)} & files
    missing = sorted(f for f in files if not (ROOT / f).is_file())
    assert not missing, f"missing: {missing}"

    clear(OUT)
    for rel in sorted(files):
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = ROOT / rel
        if rel in withheld:
            dst.write_text(json.dumps({"withheld": "portal-internal evidence (see README)", "bytes": src.stat().st_size,
                                       "sha256": hashlib.sha256(src.read_bytes()).hexdigest()}, indent=1), encoding="utf-8")
        elif rel in DEEP_DIGEST:
            dst.write_text(json.dumps(deep_digest(json.loads(src.read_text(encoding="utf-8")), DEEP_DIGEST[rel]), indent=1), encoding="utf-8")
        elif rel in DROP_KEYS:
            dst.write_text(json.dumps(drop_keys(json.loads(src.read_text(encoding="utf-8")), DROP_KEYS[rel]), indent=1), encoding="utf-8")
        else:
            shutil.copyfile(ROOT / rel, dst)

    # Privacy scan over every shipped file (text decoded leniently; PDFs via their raw bytes and pdftotext if present).
    toks = student_tokens()
    needles = portal_needles()
    problems = []
    for p in shipped(OUT):
        rel = p.relative_to(OUT).as_posix()
        raw = p.read_bytes().decode("utf-8", errors="replace")
        if p.suffix == ".pdf":
            txt = shutil.which("pdftotext") or "/mingw64/bin/pdftotext.exe"
            import subprocess
            try:
                raw = subprocess.run([txt, str(p), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
            except OSError:
                problems.append(f"{rel}: pdftotext unavailable, PDF not scanned")
                continue
        low = raw.lower()
        hit = sorted(t for t in toks if t in low)
        if hit:
            problems.append(f"{rel}: {len(hit)} student identifier(s)")
        leaked = [n for n in needles if n in raw]
        if leaked:
            problems.append(f"{rel}: {len(leaked)} portal source line(s)")
        if LOCAL_PATH.search(raw) and not rel.startswith("evidence/"):  # evidence provenance records interpreter paths
            problems.append(f"{rel}: absolute local path")
        if SECRET.search(raw):
            problems.append(f"{rel}: secret-like string")
        if PRIVATE_PATH.search(raw) and rel.startswith("evidence/"):  # docs and code may name the private folders
            problems.append(f"{rel}: private path reference")
    if problems:
        clear(OUT)
        sys.exit("privacy scan failed; artifact cleared:\n  " + "\n  ".join(problems))

    write_readme()
    sums = []
    for p in shipped(OUT):
        if p.name != "SHA256SUMS":
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT).as_posix()}")
    (OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    total = sum(p.stat().st_size for p in shipped(OUT))
    print(f"artifact: {len(sums)} files, {total / 1e6:.1f} MB, scan clean ({len(toks)} student identifiers, {len(needles)} portal source lines checked) -> {OUT}")


README = """# Living Review: artifact

Code, evidence and generated numbers for *Living Review: Carrying Code Review Comments Safely Across
Resubmissions* (Jose, Samuel, Safar and Kalyanaraman, VIT Vellore) and its extended technical report.

## Contents

| Path | What it is |
|---|---|
| `v12-ieee15/paper-v12.pdf` | The paper (16 pages) and, beside it, its LaTeX source. |
| `v11-professor-revision/paper-v11.pdf` | The extended technical report (66 pages) and its LaTeX source. |
| `v11-professor-revision/generated/` | Every macro file and generated table the two documents use. Every number in the text is a macro defined here. |
| `evidence/` | Every evidence file the build reads, except the private inputs listed below, plus the suggestion-oracle records (`evidence/v12-wpk6/`). Each JSON records the SHA-256 of the code and inputs that produced it. |
| `tools/v11/`, `tools/v12/` | Runners, analyses and builders. `tools/v11/make_v11.py` and `tools/v12/make_v12.py` rebuild both documents. |
| `review/` | The frozen protocols, recorded before the analyses they govern ran. |
| `tools/release/verify_artifact.py` | Checks `SHA256SUMS` and rebuilds the macro files from the shipped evidence. |

## Verify

    python -I -B tools/release/verify_artifact.py

The script checks every file against `SHA256SUMS`, then reruns the macro builders in a temporary copy and
compares their output with the shipped macro files. It needs Python 3.12 and NumPy. Expected differences are
listed by the script: one macro (`wiStuTrRenamed`) needs the private student rows, the reproducibility
section hashes the private selection manifest, and the state-specification tables are built from portal
source text that is shipped only as digests.

## Not included

- The 20 student-authored repositories' identities and rows. They are public GitHub repositories, but they are
  student work and are pseudonymized in the paper.
- The four internal project histories, including the review portal's source. The portal state analysis
  (`evidence/v11-wpd/*.json`) quotes portal source, file inventories and test identifiers, so each of those
  files ships as a stub with its SHA-256 and size; its generated tables (`evidence/v11-wpd/tex/`) ship. In the
  bounded-model record (`evidence/v12-wpk4/`) every quoted source line is replaced by its SHA-256 and length.
  The generator of the state analysis (`tools/v11/wpd_state.py`) embeds portal source and is not shipped.
- The controlled-edit corpus, bare clones of the public histories (re-fetch them at the pinned heads), raw
  model transcripts and the suggestion-oracle file blobs (re-fetchable by commit and path). The sampled
  old/new code windows that the models saw do ship (`evidence/v12-wpk6/llm/sample.json`).
- Third-party identity fields (commit author and committer) in the pinned CodeMapper commit record.
- The blinded 120-item human-annotation packet and its key. They sample internal and student code.

## Licence

Code: MIT. Our evidence, tables and text: CC BY 4.0. The review-suggestion records in `evidence/v12-wpk6/`
quote code and comments from ten public repositories, each under MIT or Apache-2.0 (SPDX identifiers in
`evidence/v12-wpk6/selection.json`); that material keeps its own licence and attribution.
"""


def write_readme() -> None:
    (OUT / "README.md").write_text(README, encoding="utf-8")
    # Git must store bytes exactly, or line-ending conversion breaks SHA256SUMS in clones.
    (OUT / ".gitattributes").write_text("* -text\n", encoding="utf-8")


if __name__ == "__main__":
    main()
