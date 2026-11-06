"""Can the syntax-tree reference hide a missed re-check? A check of its relocation step (R4 critic finding C2).

Run: tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/audit_reference_copies.py   (from paper-drafts/)

The reference (evidence/source-snapshot/real_history.py, `oracle`) calls a target unchanged when its statement is
aligned in the same function, paired at the same offset, or, if it left its function, when a statement with an equal
syntax tree occurs exactly once in the new version ("relocated"). The verbatim check of
audit_reference_direction.py shows the text at the reference location equals the quotation. It cannot show that this
location is the reviewed code: if the reviewed statement was deleted and an identical statement already stood
elsewhere, the reference calls the copy a move, and a real change is scored as unchanged.

For every reference-unchanged row decided by relocation, this script reads the OLD version of the public history
(bare clones in evidence/public-histories, commit lists in its manifest) and asks whether the quoted lines, compared
as stripped non-blank lines, already stood at the reference location's file before the revision, other than as the
anchor itself. Rows of the authors' own projects are reported as not checkable here (their clones are not in this
folder). Writes evidence/v11-wpa/reference-relocated-copies.json.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROWS = ["evidence/recomputed-real/results-real-v1.json", "evidence/recomputed-real/results-oss-v1.json"]
MANIFEST = "evidence/public-histories/manifest.json"
DIRECTION = "evidence/v11-wpa/reference-direction.json"
OUT = ROOT / "evidence" / "v11-wpa" / "reference-relocated-copies.json"
REQUEST = ("changed", "removed")


def stripped(text: str) -> list[str]:
    return [x.strip() for x in text.replace("\r\n", "\n").splitlines() if x.strip()]


def occurrences(lines: list[str], want: list[str]) -> int:
    n = len(want)
    return sum(lines[i:i + n] == want for i in range(len(lines) - n + 1))


class History:
    def __init__(self, name: str):
        self.path = ROOT / "evidence" / "public-histories" / name

    def git(self, *args: str) -> str:
        out = subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, check=True).stdout
        return out.decode("utf-8", "replace")

    def file(self, commit: str, path: str) -> str | None:
        try:
            return self.git("show", f"{commit}:{path}")
        except subprocess.CalledProcessError:
            return None


def main() -> None:
    inputs, rows = {}, []
    for rel in ROWS + [MANIFEST, DIRECTION]:
        inputs[rel] = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    for rel in ROWS:
        d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        rows += d["rows"] if isinstance(d, dict) else d
    manifest = {m["name"]: m for m in json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))}
    direction = json.loads((ROOT / DIRECTION).read_text(encoding="utf-8"))["data"]

    unchanged = [r for r in rows if r["cls"] not in ("edited", "gone")]
    assert len(unchanged) == direction["reference_unchanged"]
    by_event = collections.Counter(r["how"] for r in unchanged)
    relocated = [r for r in unchanged if r["how"] == "relocated"]

    histories, unavailable, introduced, suspects = {}, [], [], []
    for r in relocated:
        name, horizon, index = r["pair"].split(":")
        if name not in manifest:
            unavailable.append(r)
            continue
        commits = manifest[name]["first_parent_commits"]
        assert manifest[name]["count_matches"] and len(commits) == manifest[name]["first_parent_count"]
        old = commits[int(index)]
        hist = histories.setdefault(name, History(name))
        want = stripped(r["quotation"])
        text = hist.file(old, r["truth_at"][0])
        before = occurrences(stripped(text), want) if text is not None else 0
        if r["truth_at"][0] == r["anchor_at"][0]:
            before -= 1  # the anchor itself
        row = {"pair": r["pair"], "anchor_at": r["anchor_at"], "truth_at": r["truth_at"], "copies_before": before,
               "deployed_label": r["label"], "deployed_requests": r["label"] in REQUEST,
               "deployed_outcome": r["cascade"]["outcome"]}
        (suspects if before > 0 else introduced).append(row)

    changed = direction["reference_changed_or_deleted"]
    missed = direction["deployed_missed"]
    hidden_checked = sum(not s["deployed_requests"] for s in suspects)
    hidden_unavailable = sum(r["label"] not in REQUEST for r in unavailable)
    result = dict(
        reference_unchanged=len(unchanged),
        unchanged_by_event=dict(by_event),
        relocated=len(relocated),
        relocated_checked=len(introduced) + len(suspects),
        relocated_introduced_by_revision=len(introduced),
        relocated_copy_already_at_reference=len(suspects),
        relocated_unavailable=len(unavailable),
        unavailable_by_repo=dict(collections.Counter(r["repo"] for r in unavailable)),
        suspects_without_deployed_request=hidden_checked,
        unavailable_without_deployed_request=hidden_unavailable,
        deployed_missed=missed,
        deployed_missed_pct=100 * missed / changed,
        missed_pct_if_checked_suspects_are_changes=100 * (missed + hidden_checked) / (changed + len(suspects)),
        missed_pct_if_all_unverified_are_changes=100 * (missed + hidden_checked + hidden_unavailable)
        / (changed + len(suspects) + len(unavailable)),
        suspects=suspects,
    )
    OUT.write_text(json.dumps({"provenance": {"script": "tools/v11/audit_reference_copies.py", "inputs_sha256": inputs,
                                              "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                               "data": result}, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "suspects"}, indent=2))


if __name__ == "__main__":
    main()
