"""WP D scenario harness: drives the pinned application through its own HTTP API.

Nothing in the pinned app is modified. Submissions go through the real preflight and
submission routes (real ZIP validation, artifact store and SubmissionFile rows), analysis
arrives as signed partner bundles through the real import route, and review state changes
go through the faculty Studio routes, on the app's own in-memory SQLite test configuration.
The PostgreSQL concurrency scenario is service-level; see test_wpd_scenarios.py.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from wpd_common import OUT

SCENARIOS = OUT / "scenarios"


def sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def archive(src: dict[str, str | bytes]) -> bytes:
    """The pinned tests' valid VITS-style archive with the given source files substituted."""
    from tests.artifacts.test_submission_artifacts import _archive
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_archive())) as base, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as new:
        for name in base.namelist():
            if name not in src:
                new.writestr(name, base.read(name))
        for name, text in src.items():
            new.writestr(name, text)
    return stream.getvalue()


def record(name: str, claim: str, claim_holds: bool, observed: dict, *, engine: str = "sqlite", note: str = "") -> None:
    """One scenario outcome: the paper claim checked, whether it held, and what was observed."""
    SCENARIOS.mkdir(parents=True, exist_ok=True)
    (SCENARIOS / f"{name}.json").write_text(json.dumps(
        {"scenario": name, "claim": claim, "claim_holds": bool(claim_holds), "engine": engine,
         "note": note, "observed": observed}, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


class Studio:
    """A faculty member, a student team and a partner analyser on one project."""

    def __init__(self, tmp_path: Path, monkeypatch):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from fastapi.testclient import TestClient
        from tests.artifacts.test_submission_artifacts import _app

        self.app, self.student = _app(tmp_path, monkeypatch)

        async def _queued_only(*_args, **_kwargs):
            return "wpd-queued"
        monkeypatch.setattr("app.routers.review_copilot._schedule_deep_review_run", _queued_only)
        self._key = Ed25519PrivateKey.generate()
        monkeypatch.setenv("VCAP_ANALYSIS_SIGNING_KEYS_JSON", json.dumps(
            {"cdc-trace": {"test": self._b64(self._key.public_key().public_bytes_raw())}}))
        from app.shared.auth.deps import issue_token
        self.faculty = {"Authorization": "Bearer " + issue_token(
            {"sub": "artifact-faculty", "role": "guide"}, secret=os.environ["RECAP_JWT_SECRET"])}
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.versions: list[str] = []
        self._n = 0

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def close(self):
        self.client.__exit__(None, None, None)

    # -- student side ---------------------------------------------------
    def stage(self, src: dict[str, str | bytes]):
        return self.client.post("/student/projects/artifact-project/preflight", headers=self.student,
                                files={"file": ("project.zip", archive(src), "application/zip")},
                                data={"verify_citations": "false"})

    def submit(self, src: dict[str, str | bytes]) -> str:
        if self.versions:
            for action in ("start_verification", "reject"):
                decided = self.client.post(f"/review/reports/{self.versions[-1]}/decision",
                                           headers=self.faculty, json={"action": action})
                assert decided.status_code == 200, decided.text
        staged = self.stage(src)
        assert staged.status_code == 200, staged.text
        self._n += 1
        done = self.client.post("/student/projects/artifact-project/submissions", headers=self.student,
                                json={"staged_artifact_id": staged.json()["staged_artifact"]["id"],
                                      "warning_acknowledged": True, "idempotency_key": f"wpd-submission-{self._n:04d}"})
        assert done.status_code == 201, done.text
        self.versions.append(done.json()["version_id"])
        # Fixture configuration, not app code: the per-version attempt limit (default 3) is
        # raised so one project can hold the five-version chains these scenarios need.
        import uuid
        from app.modules.reports.models import ReportVersion
        with self.app.state.session_factory() as session:
            session.get(ReportVersion, uuid.UUID(self.versions[-1])).max_tries = 10
            session.commit()
        return self.versions[-1]

    # -- partner analyser ----------------------------------------------
    def analyse(self, rv_id: str, findings: list[dict]) -> None:
        """findings: [{"claim": str, "anchors": [code anchors]}] imported as UNSUPPORTED partner findings."""
        from app.modules.artifacts.models import SubmissionArtifact
        from app.modules.review_copilot.services.analysis_bundles import AnalysisBundle, canonical_bytes
        with self.app.state.session_factory() as session:
            archive_sha = session.query(SubmissionArtifact).filter_by(report_version_id=rv_id).one().archive_sha256
        self._n += 1
        bundle = AnalysisBundle.model_validate({
            "schema_version": "vcap.analysis-bundle.v1", "bundle_id": f"wpd-{self._n}-{rv_id[:8]}",
            "producer_id": "cdc-trace", "producer_commit": "a" * 40, "method_version": "counterfactual-v1",
            "report_version_id": rv_id, "project_id": "artifact-project", "archive_sha256": archive_sha,
            "state": "completed", "limitations": [],
            "findings": [{"id": f"claim-{self._n}-{n}", "claim": f["claim"], "verdict": "UNSUPPORTED",
                          "explanation": "C=0.", "independent_count": 0, "channels": ["NAME"],
                          "anchors": f.get("anchors", [])} for n, f in enumerate(findings, 1)],
            "signature": {"algorithm": "Ed25519", "key_id": "test", "value": "pending"}})
        body = bundle.model_dump()
        body["signature"]["value"] = self._b64(self._key.sign(canonical_bytes(bundle)))
        imported = self.client.post(f"/review/reports/{rv_id}/analysis-bundles", headers=self.faculty, json=body)
        assert imported.status_code == 201, imported.text

    # -- faculty side ---------------------------------------------------
    def url(self, rv_id: str) -> str:
        return f"/review/reports/{rv_id}/studio"

    def doc(self, rv_id: str) -> dict:
        got = self.client.get(self.url(rv_id), headers=self.faculty)
        assert got.status_code == 200, got.text
        return got.json()

    def compose(self, rv_id: str) -> dict:
        got = self.client.post(f"{self.url(rv_id)}/compose", headers=self.faculty)
        assert got.status_code == 200, got.text
        return got.json()

    def create(self, rv_id: str, **fields) -> dict:
        got = self.client.post(f"{self.url(rv_id)}/items", headers=self.faculty, json=fields)
        assert got.status_code == 201, got.text
        return got.json()

    def patch(self, rv_id: str, item: dict, **changes) -> dict:
        got = self.client.patch(f"{self.url(rv_id)}/items/{item['id']}", headers=self.faculty,
                                json={"base_revision": item["revision"], "changes": changes})
        assert got.status_code == 200, got.text
        return got.json()

    def revisions(self, rv_id: str, item_id: str) -> list[dict]:
        got = self.client.get(f"{self.url(rv_id)}/items/{item_id}/revisions", headers=self.faculty)
        assert got.status_code == 200, got.text
        body = got.json()
        return body.get("revisions", body) if isinstance(body, dict) else body

    def upload(self, rv_id: str, data: bytes, filename: str, **form) -> dict:
        got = self.client.post(f"{self.url(rv_id)}/attachments", headers=self.faculty,
                               files={"file": (filename, data, "application/octet-stream")},
                               data={k: str(v) for k, v in form.items()})
        assert got.status_code == 201, got.text
        return got.json()

    def link(self, rv_id: str, **body) -> dict:
        got = self.client.post(f"{self.url(rv_id)}/links", headers=self.faculty, json=body)
        assert got.status_code == 201, got.text
        return got.json()


def code_anchor(path: str, text: str, start: int, end: int) -> dict:
    lines = text.splitlines()
    return {"family": "code", "path": path, "line_start": start, "line_end": end,
            "content_hash": sha(text), "quotation": "\n".join(lines[start - 1:end])}

