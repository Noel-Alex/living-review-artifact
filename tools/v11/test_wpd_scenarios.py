"""WP D3/D4 scenarios against the pinned application (imported, never modified).

Each test records one JSON per scenario under evidence/v11-wpd/scenarios/ with the paper
claim it checks, whether that claim held, and the raw observations. Tests assert the
implemented behaviour that was observed, so a scenario that refutes a paper claim still
passes as a characterisation and reports ``claim_holds: false``.
"""
from __future__ import annotations

import os
import struct
import threading

import pytest

from wpd_harness import Studio, code_anchor, record

PATH = "src/app.py"
V1 = ('def setup():\n    return {"debug": False}\n\n\n'
      "def answer(x):\n    total = x * 2\n    return total + 40\n")
V2_MOVED = ("def helper(y):\n    # a new helper above the anchored code\n    return y\n\n\n" + V1)
V3_CHANGED = V2_MOVED.replace("total = x * 2", "total = x * 3")
V4_REMOVED = ("def helper(y):\n    # a new helper above the anchored code\n    return y\n\n\n"
              'def setup():\n    return {"debug": False}\n')
WAV = b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8) \
      + b"data" + struct.pack("<I", 0)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _carried(doc, title):
    return next(i for i in doc["items"] if i["title"] == title)


def _anchor_view(item):
    return [{k: e.get(k) for k in ("path", "line_start", "line_end", "match", "similarity", "quotation")}
            for e in item["evidence"] if e.get("path")]


def test_three_version_chain_and_media_notes(tmp_path, monkeypatch):
    """SM1/SA4: anchor moves, then changes, then disappears; issue, evidence history and media follow."""
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1})
    s.doc(v1)
    issue = s.create(v1, title="Explain the constant", body="Why does answer add 40?", severity="minor",
                     category="other", evidence=[code_anchor(PATH, V1, 5, 7)])
    voice = s.upload(v1, WAV, "voice.wav", title="Voice note", anchor_type="review_item", item_id=issue["id"])
    image = s.upload(v1, PNG, "sketch.png", title="Image note", anchor_type="code_range",
                     path=PATH, line_start=5, line_end=7)
    steps = []
    for src, expected in ((V2_MOVED, "moved"), (V3_CHANGED, "changed"), (V4_REMOVED, "removed")):
        rv = s.submit({PATH: src})
        doc = s.doc(rv)
        item = _carried(doc, "Explain the constant")
        atts = {a["title"]: a for a in doc["attachments"]}
        steps.append({"expected_label": expected, "status": item["status"], "carried": item["carried"],
                      "anchors": _anchor_view(item),
                      "voice": {k: atts["Voice note"].get(k) for k in ("anchor_type", "item_id", "note")},
                      "voice_linked_to_carried_issue": atts["Voice note"]["item_id"] == item["id"],
                      "image": {k: atts["Image note"].get(k) for k in ("anchor_type", "path", "line_start", "line_end", "note")}})
    first = s.doc(v1)
    original = _carried(first, "Explain the constant")
    labels = [st["anchors"][0]["match"] if st["anchors"] else None for st in steps]
    statuses = [st["status"] for st in steps]
    quotations = [st["anchors"][0]["quotation"] if st["anchors"] else None for st in steps]
    observed = {"steps": steps, "labels": labels, "statuses": statuses,
                "v1_issue_after_chain": {"status": original["status"], "anchors": _anchor_view(original)},
                "quotation_after_changed_is_new_text": quotations[1] is not None and "x * 3" in quotations[1],
                "quotation_after_removed": quotations[2]}
    holds = (labels == ["moved", "changed", "removed"] and statuses == ["open", "needs_recheck", "needs_recheck"]
             and all(st["voice_linked_to_carried_issue"] for st in steps))
    record("three_version_chain_media", "An anchor that moves, changes and disappears is labelled moved, changed, "
           "removed; the issue stays open until faculty act, needs re-check after change; voice and image notes "
           "follow the carried issue and code.", holds, observed)
    assert labels == ["moved", "changed", "removed"]
    assert statuses == ["open", "needs_recheck", "needs_recheck"]
    assert observed["quotation_after_changed_is_new_text"]
    assert original["status"] == "open" and "x * 2" in original["evidence"][0]["quotation"]
    s.close()


def test_repeated_composition_is_idempotent(tmp_path, monkeypatch):
    """SA3: composing the same version three times yields no duplicates and unchanged content."""
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1})
    s.analyse(v1, [{"claim": "The system computes the answer with a neural planner.",
                    "anchors": [code_anchor(PATH, V1, 5, 7)]}])
    s.doc(v1)
    issue = s.create(v1, title="Explain the constant", body="Why 40?", evidence=[code_anchor(PATH, V1, 5, 7)])
    s.link(v1, kind="link", title="Design notes", url="https://example.org/notes", anchor_type="code_range",
           path=PATH, line_start=5, line_end=7)
    v2 = s.submit({PATH: V3_CHANGED})
    first = s.doc(v2)
    snaps = []
    for _ in range(3):
        d = s.compose(v2)
        snaps.append({"items": sorted((i["id"], i["status"], i["revision"], i["body"]) for i in d["items"]),
                      "attachments": sorted((a["id"], a["note"]) for a in d["attachments"])})
    base = {"items": sorted((i["id"], i["status"], i["revision"], i["body"]) for i in first["items"]),
            "attachments": sorted((a["id"], a["note"]) for a in first["attachments"])}
    same = all(sn == base for sn in snaps)
    record("repeated_composition", "Composing the same version repeatedly creates no duplicate issues or "
           "attachments and leaves content unchanged.", same,
           {"items_first": len(base["items"]), "attachments_first": len(base["attachments"]),
            "items_after_each": [len(sn["items"]) for sn in snaps],
            "attachments_after_each": [len(sn["attachments"]) for sn in snaps], "identical": same})
    assert same
    s.close()


def _claim(text):
    return [{"claim": text, "anchors": [code_anchor(PATH, V1, 5, 7)]}]


def _partner(doc, needle):
    return [i for i in doc["items"] if needle in i["body"] and i["origin"] == "partner"]


def test_dismissal_memory_cases(tmp_path, monkeypatch):
    """SM3: when does dismissal memory suppress a finding raised again?"""
    planner = "The system computes the answer with a neural planner."
    prefix = ("The evaluation pipeline reports improved accuracy on every benchmark split and claims that the "
              "improvement is due to the retrieval component, which is described in detail in the methods "
              "chapter of the report and in the appendix, ")
    alpha, beta = prefix + "measured with exact match.", prefix + "measured with a completely different metric."
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1})
    s.analyse(v1, _claim(planner) + _claim(alpha))
    d1 = s.doc(v1)
    for needle in (planner, alpha):
        s.patch(v1, _partner(d1, needle)[0], status="dismissed")
    # (e) a faculty-written issue with a detector heading, dismissed
    from app.modules.review_studio.service import finding_title
    faculty_title = finding_title("Every request is logged to disk.", "paper_vs_code")
    fac = s.create(v1, title=faculty_title, body="Logging claim, faculty wording.", category="paper_vs_code",
                   evidence=[code_anchor(PATH, V1, 1, 2)])
    s.patch(v1, fac, status="dismissed")

    moved_src = "# moved down\n\n\n" + V1
    v2 = s.submit({PATH: moved_src})
    s.analyse(v2, [{"claim": planner, "anchors": [code_anchor(PATH, moved_src, 1, 3)]},   # (a) other location
                   {"claim": beta, "anchors": [code_anchor(PATH, moved_src, 8, 10)]},     # (c) 200-char collision
                   {"claim": "Every request is logged to disk.", "anchors": [code_anchor(PATH, moved_src, 4, 5)]}])
    d2 = s.compose(v2)
    a = _partner(d2, planner)
    c = _partner(d2, beta)
    e = _partner(d2, "Every request is logged")
    # (d) not raised on v3, raised again on v4
    v3 = s.submit({PATH: moved_src})
    s.analyse(v3, [{"claim": "Some unrelated claim about caching layers.", "anchors": []}])
    s.compose(v3)
    v4 = s.submit({PATH: moved_src})
    s.analyse(v4, [{"claim": planner, "anchors": [code_anchor(PATH, moved_src, 8, 10)]}])
    d4 = s.compose(v4)
    d = _partner(d4, planner)
    observed = {
        "a_same_key_other_location": [i["status"] for i in a],
        "c_distinct_finding_sharing_first_200_chars": {"statuses": [i["status"] for i in c],
                                                        "suppressed": bool(c) and c[0]["status"] == "dismissed"},
        "d_raised_again_two_versions_later": [i["status"] for i in d],
        "e_faculty_dismissed_same_heading_then_detector_raises_it": [i["status"] for i in e],
        "a_note": a[0]["body"][-160:] if a else None,
    }
    record("dismissal_memory", "A dismissed finding raised again on a later version arrives dismissed; the key is "
           "category plus normalised title (v10 wording).", False, observed,
           note="Key is category + first body paragraph (200 normalised chars) for partner/system findings and "
                "category + title for faculty/agent items; memory spans only the immediately previous version.")
    assert [i["status"] for i in a] == ["dismissed"]
    assert observed["c_distinct_finding_sharing_first_200_chars"]["suppressed"]
    assert [i["status"] for i in d] == ["open"]
    assert [i["status"] for i in e] == ["open"]
    s.close()


def test_resolved_issue_reintroduced(tmp_path, monkeypatch):
    """SM4: a finding raised again after faculty resolved it, across and within versions."""
    planner = "The system computes the answer with a neural planner."
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1})
    s.analyse(v1, _claim(planner))
    d1 = s.doc(v1)
    resolved_v1 = s.patch(v1, _partner(d1, planner)[0], status="resolved")
    v2 = s.submit({PATH: V3_CHANGED})
    s.analyse(v2, [{"claim": planner, "anchors": [code_anchor(PATH, V3_CHANGED, 10, 12)]}])
    d2 = s.compose(v2)
    across = _partner(d2, planner)
    history_v1 = s.revisions(v1, resolved_v1["id"])
    v1_status = s.doc(v1)["items"][0]["status"]
    s.close()

    # within one version: the carried issue is resolved, then a late analysis raises it again
    s2 = Studio(tmp_path / "within", monkeypatch)
    w1 = s2.submit({PATH: V1})
    s2.analyse(w1, _claim(planner))
    s2.doc(w1)
    w2 = s2.submit({PATH: V1})
    carried = [i for i in s2.doc(w2)["items"] if i["carried"]][0]
    s2.patch(w2, carried, status="resolved")
    # the late finding points at overlapping lines, so the "raised again" merge path applies
    s2.analyse(w2, [{"claim": planner, "anchors": [code_anchor(PATH, V1, 6, 7)]}])
    dw = s2.compose(w2)
    within = _partner(dw, planner)
    within_revisions = [{k: r.get(k) for k in ("revision", "operation", "actor_type")}
                        for r in s2.revisions(w2, within[0]["id"])] if within else []
    observed = {
        "across_versions_new_issue": [{"status": i["status"], "carried": i["carried"]} for i in across],
        "v1_resolved_history_operations": [r.get("operation") for r in history_v1],
        "v1_resolved_still_stored": v1_status,
        "within_version_items_after_late_finding": [{"status": i["status"], "carried": bool(i["carried"]),
                                                     "anchors": _anchor_view(i)} for i in within],
        "within_version_revisions": within_revisions,
    }
    holds = (len(across) == 1 and across[0]["status"] == "open" and across[0]["carried"] is None)
    record("resolved_reintroduced", "A finding raised again after faculty resolved it creates a new issue, and the "
           "resolved issue's history stays visible.", holds, observed,
           note="Across versions the new issue is not linked to the resolved one. Within one version a resolved "
                "carried issue absorbs a re-raised finding with overlapping evidence: no new issue is created and "
                "the issue stays resolved; within_version_revisions shows whether the system rewrote its evidence.")
    assert holds
    assert len(within) == 1 and within[0]["status"] == "resolved"
    s2.close()


def test_multi_anchor_supporting_change(tmp_path, monkeypatch):
    """SM5: only a supporting anchor changes."""
    other = "def unrelated():\n    return 'stable'\n"
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1, "src/other.py": other})
    s.doc(v1)
    s.create(v1, title="Two places", body="Primary in other.py, support in app.py.",
             evidence=[code_anchor("src/other.py", other, 1, 2), code_anchor(PATH, V1, 5, 7)])
    v2 = s.submit({PATH: V3_CHANGED, "src/other.py": other})
    item = _carried(s.doc(v2), "Two places")
    observed = {"status": item["status"], "anchors": _anchor_view(item)}
    record("multi_anchor_supporting_change", "An issue is returned for re-check when any of its anchors changes, "
           "including a supporting one.", item["status"] == "needs_recheck", observed,
           note="The Studio headline label (anchorHtml) shows only the first code anchor; per-anchor notes appear "
                "in the evidence list.")
    assert item["status"] == "needs_recheck"
    assert [a["match"] for a in observed["anchors"]] == ["exact", "changed"]
    s.close()


def test_normalisation_cases(tmp_path, monkeypatch):
    """D4: CRLF, BOM, trailing newline, oversize text file and non-UTF-8 bytes through real ingestion."""
    big = V1 + "".join(f"# padding line {n:06d} keeps this file large but unchanged\n" for n in range(8_000))
    cases = {
        "crlf": V1.replace("\n", "\r\n").encode(),
        "bom": b"\xef\xbb\xbf" + V1.encode(),
        "no_trailing_newline": V1.rstrip("\n").encode(),
    }
    observed = {}
    for name, data in cases.items():
        s = Studio(tmp_path / name, monkeypatch)
        v1 = s.submit({PATH: V1})
        s.doc(v1)
        s.create(v1, title="First lines", body="b", evidence=[code_anchor(PATH, V1, 1, 2)])
        s.create(v1, title="Body lines", body="b", evidence=[code_anchor(PATH, V1, 5, 7)])
        v2 = s.submit({PATH: data})
        doc = s.doc(v2)
        observed[name] = {t: {"match": _anchor_view(_carried(doc, t))[0]["match"],
                              "status": _carried(doc, t)["status"]} for t in ("First lines", "Body lines")}
        s.close()
    s = Studio(tmp_path / "big", monkeypatch)
    v1 = s.submit({PATH: big})
    s.doc(v1)
    s.create(v1, title="Body lines", body="b", evidence=[code_anchor(PATH, big, 5, 7)])
    v2 = s.submit({PATH: big})
    item = _carried(s.doc(v2), "Body lines")
    observed["unchanged_file_over_400000_bytes"] = {"bytes": len(big.encode()), "match": _anchor_view(item)[0]["match"]
                                                    if _anchor_view(item) else [e.get("match") for e in item["evidence"]],
                                                    "status": item["status"]}
    bad = s.stage({PATH: b"def f():\n    return '\xff'\n"})
    observed["non_utf8_text_file"] = {"preflight_status": bad.status_code, "body": bad.text[:300]}
    s.close()
    record("normalisation", "Encoding and newline variants of unchanged code keep their anchors; non-UTF-8 files "
           "are skipped, so their anchors become removed (lead's preliminary reading).", False, observed,
           note="Recorded labels are the implemented behaviour; see results note for the specification.")
    assert observed["crlf"]["Body lines"]["match"] == "exact"


def test_uncomposed_intermediate_version(tmp_path, monkeypatch):
    """Carry-forward reads only the immediately previous version's review document."""
    s = Studio(tmp_path, monkeypatch)
    v1 = s.submit({PATH: V1})
    s.doc(v1)
    s.create(v1, title="Explain the constant", body="Why 40?", evidence=[code_anchor(PATH, V1, 5, 7)])
    v2 = s.submit({PATH: V1})   # never composed: analysis pipeline did not run and nobody opened it
    v3 = s.submit({PATH: V1})
    d3 = s.doc(v3)
    carried_v3 = [i["title"] for i in d3["items"] if i["carried"]]
    d2 = s.doc(v2)               # opening v2 later carries v1's issue into v2 ...
    carried_v2 = [i["title"] for i in d2["items"] if i["carried"]]
    d3_again = s.doc(v3)         # ... but v3, already composed, is not updated until recomposed
    carried_v3_after = [i["title"] for i in d3_again["items"] if i["carried"]]
    carried_v3_recomposed = [i["title"] for i in s.compose(v3)["items"] if i["carried"]]
    observed = {"v3_carried_when_v2_uncomposed": carried_v3, "v2_carried_when_opened_later": carried_v2,
                "v3_carried_after_v2_opened": carried_v3_after, "v3_carried_after_explicit_recompose": carried_v3_recomposed}
    record("uncomposed_intermediate_version", "An open issue reaches every later version until faculty close it.",
           bool(carried_v3), observed,
           note="In production each version is composed after its analysis pipeline; this case needs that pipeline to fail "
                "and the version to stay unopened.")
    assert carried_v3 == [] and carried_v2 == ["Explain the constant"]
    s.close()


PG_URL = os.environ.get("WPD_PG_URL")


def _pg_schema(engine):
    """Every table the app's models declare, on PostgreSQL with the real column types."""
    import sys
    from sqlalchemy import MetaData
    import app.main  # noqa: F401 - loads every router and model module
    metas = {id(m): m for name, mod in list(sys.modules.items()) if name.startswith("app.")
             for m in (getattr(v, "metadata", None) for v in vars(mod).values()) if isinstance(m, MetaData)}
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    for _ in range(3):  # cross-metadata foreign keys resolve once their targets exist
        for meta in metas.values():
            try:
                meta.create_all(engine)
            except Exception:
                pass
    for meta in metas.values():
        meta.create_all(engine)


@pytest.mark.skipif(not PG_URL, reason="needs a disposable local PostgreSQL (WPD_PG_URL)")
def test_concurrent_and_interrupted_composition_postgres(monkeypatch):
    """SA2/SA3 on PostgreSQL, where SELECT ... FOR UPDATE and the unique origin_ref constraint are enforced.

    Service level: composition, carry-forward, item creation, version locking and constraints are the
    pinned code on a real PostgreSQL server. Only the file loader (carry.version_files and the report
    reader) is replaced by an in-memory map built with the loader's own rules (sha256 of raw bytes,
    strict UTF-8). Each worker uses its own connection and transaction.
    """
    import time
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from wpd_harness import sha
    engine = create_engine(PG_URL, pool_size=8)
    _pg_schema(engine)
    from app.modules.reports.models import ProjectReport, ReportVersion
    from app.modules.review_studio import carry, service
    from app.modules.review_studio.models import ReviewDocument, ReviewItem, ReviewItemRevision

    with Session(engine) as session:
        report = ProjectReport(project_id="pg-project", guide_id="pg-faculty", student_id="pg-student",
                               title="PostgreSQL fixture", review_milestone="R1")
        session.add(report)
        session.flush()
        v1 = ReportVersion(report_id=report.id, version=1, submission_status="rejected", compilation_status="idle")
        session.add(v1)
        session.flush()
        v2 = ReportVersion(report_id=report.id, version=2, previous_version_id=v1.id,
                           submission_status="submitted", compilation_status="idle")
        session.add(v2)
        session.flush()
        rv1, rv2 = str(v1.id), str(v2.id)
        doc1 = service.ensure_document(session, rv1, "pg-project")
        for n, (start, end) in enumerate(((1, 2), (5, 7), (5, 6)), 1):
            service.create_item(session, doc1, {"title": f"Issue {n}", "body": f"Body {n}",
                                "evidence": [code_anchor(PATH, V1, start, end)]},
                                origin="faculty", actor_id="pg-faculty")
        session.commit()
    files = {rv1: {PATH: (sha(V1), V1)}, rv2: {PATH: (sha(V3_CHANGED), V3_CHANGED)}}
    monkeypatch.setattr(carry, "version_files", lambda session, rv_id: dict(files[str(rv_id)]))
    monkeypatch.setattr(carry, "_new_version_sources", lambda session, rv_id: (dict(files[str(rv_id)]), ""))

    # 1. interrupted transaction: crash after the carried issues are written, before commit
    real_attach = carry.carry_attachments

    def _crash(*args, **kwargs):
        raise RuntimeError("simulated worker crash during composition")
    monkeypatch.setattr(carry, "carry_attachments", _crash)
    crashed = None
    with Session(engine) as session:
        try:
            service.compose(session, rv2, "pg-project")
            session.commit()
        except RuntimeError as exc:
            crashed = str(exc)
            session.rollback()
    with Session(engine) as session:
        docs_after_crash = session.scalar(select(func.count()).select_from(ReviewDocument)
                                          .where(ReviewDocument.report_version_id == rv2))
    monkeypatch.setattr(carry, "carry_attachments", real_attach)

    # 2. two workers compose the same version at once; the first is slowed inside carry-forward
    events, errors, lock = [], [], threading.Lock()
    real_carry = carry.carry_forward

    def traced_carry(session, document, rv_id):
        name = threading.current_thread().name
        with lock:
            first = not any(e[1] == "carry_start" for e in events)
            events.append((name, "carry_start", time.monotonic()))
        if first:
            time.sleep(1.5)
        return real_carry(session, document, rv_id)
    monkeypatch.setattr(carry, "carry_forward", traced_carry)
    barrier = threading.Barrier(2)

    def worker():
        name = threading.current_thread().name
        with Session(engine) as session:
            try:
                barrier.wait(timeout=30)
                with lock:
                    events.append((name, "compose_call", time.monotonic()))
                service.compose(session, rv2, "pg-project")
                session.commit()
                with lock:
                    events.append((name, "commit", time.monotonic()))
            except Exception as exc:  # recorded, not hidden
                session.rollback()
                errors.append(f"{name}: {type(exc).__name__}: {exc}"[:400])
    threads = [threading.Thread(target=worker, name=f"worker-{n}") for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    with Session(engine) as session:
        doc = session.scalar(select(ReviewDocument).where(ReviewDocument.report_version_id == rv2))
        items = session.scalars(select(ReviewItem).where(ReviewItem.document_id == doc.id)).all()
        refs = [i.origin_ref for i in items]
        statuses = sorted(i.status for i in items)
        creates = session.scalar(select(func.count()).select_from(ReviewItemRevision)
                                 .where(ReviewItemRevision.item_id.in_([i.id for i in items]),
                                        ReviewItemRevision.operation == "create"))
    t0 = min(e[2] for e in events)
    timeline = [(n, what, round(at - t0, 3)) for n, what, at in sorted(events, key=lambda e: e[2])]
    starts = [e for e in timeline if e[1] == "carry_start"]
    first_commit = [c[2] for c in timeline if c[1] == "commit" and starts and c[0] == starts[0][0]]
    serialised = len(starts) == 2 and bool(first_commit) and starts[1][2] >= first_commit[0] - 0.05
    observed = {"interrupted": {"error": crashed, "documents_after_rollback": docs_after_crash},
                "concurrent": {"errors": errors, "items": len(items),
                               "carried": sum(1 for r in refs if (r or "").startswith("carry:")),
                               "duplicate_origin_refs": len(refs) - len(set(refs)), "statuses": statuses,
                               "create_revisions": creates, "timeline_seconds": timeline,
                               "second_carry_started_after_first_commit": serialised},
                "server_version": list(engine.dialect.server_version_info or ())}
    holds = docs_after_crash == 0 and not errors and len(refs) == len(set(refs)) and len(items) == 3 and serialised
    record("concurrency_postgres", "Concurrent composition of one version creates no duplicates; an interrupted "
           "composition leaves no partial state.", holds, observed, engine="postgresql",
           note="Service-level on PostgreSQL; only the file loader is an in-memory map.")
    assert docs_after_crash == 0
    assert len(refs) == len(set(refs)) and len(items) == 3
    engine.dispose()
