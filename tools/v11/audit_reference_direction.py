"""Direction of syntax-tree reference error on the real-history corpus (R03 venue review, major 7).

Run: python -I -B tools/v11/audit_reference_direction.py   (from paper-drafts/)

The reference (evidence/source-snapshot/real_history.py) calls a target unchanged only when the quoted lines,
whitespace-stripped, equal the lines at the reference location (and the quotation occurs once in that file).
This script checks that property on every saved real-history row, and splits the deployed cascade's missed
re-checks by the reference event that established the target's identity:
  aligned  - an equal syntax tree at the aligned position (identity not in doubt; text changed outside the tree)
  edited   - same-type pairing inside an equal-cardinality replacement (can pair unrelated statements)
  deleted  - no unique equal tree in any function body of the new version
Among the targets the reference calls changed, an error can only turn an unchanged target into a changed or
deleted one, so it can add a missed re-check; the lower bound counts only the `aligned` misses. Whether an
"unchanged" target is the reviewed code is a separate question, checked by audit_reference_copies.py (relocated
targets can be pre-existing copies, which can hide a miss).
Writes evidence/v11-wpa/reference-direction.json.
"""
from __future__ import annotations

from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROWS = ["evidence/recomputed-real/results-real-v1.json", "evidence/recomputed-real/results-oss-v1.json"]
ERRORS = "evidence/v11-wpa/error-analysis.json"
OUT = ROOT / "evidence" / "v11-wpa" / "reference-direction.json"


def stripped(text: str) -> list[str]:
    return [x.strip() for x in text.splitlines() if x.strip()]


def main() -> None:
    inputs = {}
    rows = []
    for rel in ROWS:
        raw = (ROOT / rel).read_bytes()
        inputs[rel] = hashlib.sha256(raw).hexdigest()
        d = json.loads(raw.decode("utf-8"))
        rows += d["rows"] if isinstance(d, dict) else d
    raw = (ROOT / ERRORS).read_bytes()
    inputs[ERRORS] = hashlib.sha256(raw).hexdigest()
    err = json.loads(raw.decode("utf-8"))
    err = err.get("data", err)

    unchanged = [r for r in rows if r["cls"] not in ("edited", "gone")]
    changed = [r for r in rows if r["cls"] in ("edited", "gone")]
    certified = sum(stripped(r["quotation"]) == stripped(r["truth_text"]) for r in unchanged)
    differ = sum(stripped(r["quotation"]) != stripped(r["truth_text"]) for r in changed)
    assert certified == len(unchanged) and differ == len(changed), (certified, len(unchanged), differ, len(changed))

    missed = err["missed_cases"]
    assert len(missed) == err["missed_n"]
    by_event = Counter(c["how"] for c in missed)
    assert set(by_event) <= {"aligned", "edited", "deleted"}, by_event
    result = dict(
        rows=len(rows),
        reference_unchanged=len(unchanged), reference_unchanged_textually_certified=certified,
        reference_changed_or_deleted=len(changed), reference_changed_text_differs=differ,
        changed_by_event=dict(Counter(r["how"] for r in changed)),
        deployed_missed=len(missed), deployed_missed_by_event=dict(by_event),
        deployed_missed_pct=100 * len(missed) / len(changed),
        adverse_bound_missed=by_event.get("aligned", 0),
        adverse_bound_missed_pct=100 * by_event.get("aligned", 0) / len(changed),
    )
    OUT.write_text(json.dumps({"provenance": {"script": "tools/v11/audit_reference_direction.py", "inputs_sha256": inputs,
                                              "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                               "data": result}, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
