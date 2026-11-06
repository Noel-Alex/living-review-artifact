"""Fetch the ReviewAnchorBench third-party source blobs (fetch-only, never redistributed).

Reads the package's third_party_evidence_manifest.json, downloads each pinned raw GitHub URL,
checks size and SHA-256, and stores verified bytes as <sha256>.bin. Failures are recorded,
not skipped silently. Existing verified blobs are kept.

Usage: python -I -B rab_fetch.py <manifest.json> <out_dir>
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path


def main() -> int:
    manifest, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    records = json.loads(manifest.read_text(encoding="utf-8"))["records"]
    ok, failed = 0, []
    for item in records:
        sha = item["blob_sha256"]
        target = out / f"{sha}.bin"
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
            ok += 1
            continue
        err = None
        for attempt in range(3):
            try:
                body = urllib.request.urlopen(item["download_url"], timeout=60).read()
                if len(body) == item["size_bytes"] and hashlib.sha256(body).hexdigest() == sha:
                    target.write_bytes(body)
                    err = None
                    break
                err = f"integrity mismatch (size {len(body)})"
            except Exception as exc:  # network errors are recorded, then retried
                err = f"{type(exc).__name__}: {exc}"
            time.sleep(2 * (attempt + 1))
        if err:
            failed.append({"blob_sha256": sha, "url": item["download_url"], "error": err})
        else:
            ok += 1
    report = {"manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
              "record_n": len(records), "verified_n": ok, "failed": failed}
    (out.parent / "fetch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("record_n", "verified_n")}, indent=2), "failed", len(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
