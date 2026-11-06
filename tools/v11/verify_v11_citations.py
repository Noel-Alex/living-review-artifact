"""Identity check for the references added in v11, following the v10 citation-audit procedure.

Fetches Crossref (DOI) and arXiv API records and the cited documentation pages, saves every raw
response with its SHA-256 under evidence/v11-wpg2/citation-audit/, and compares title words and
author surnames with the bibliography entry. Prints one line per reference.

Run: python -I -B tools/v11/verify_v11_citations.py   (from paper-drafts/; needs network)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/v11-wpg2/citation-audit"
UA = {"User-Agent": "living-review-citation-audit/1.0"}

REFS = [
    # Peer-reviewed versions replace arXiv records (professor's reference feedback, 2026-11-06).
    ("hu2026codemapper", "doi", "10.1145/3744916.3773267", "CodeMapper: A language-agnostic approach to mapping code regions across commits", ["Hu", "Pradel"]),
    ("horvath2024metamanager", "doi", "10.1145/3613904.3642676", "Meta-Manager: A tool for collecting and exploring meta information about code", ["Horvath", "Macvean", "Myers"]),
    ("misback2024magic", "doi", "10.1145/3660829.3660836", "Magic Markup: Maintaining document-external markup with an LLM", ["Misback", "Tatlock", "Tanimoto"]),
    ("islam2025historyfinder", "doi", "10.1145/3744916.3773238", "HistoryFinder: Advancing method-level source code history generation with accurate oracles and enhanced algorithm", ["Islam", "Aowal", "Uddin", "Chowdhury"]),
    ("sun2026recite", "doi", "10.1145/3832783.3837474", "We must have missed this comment: Detecting and repairing stale function references in Linux kernel comments", ["Sun", "Lawall", "Lo"]),
    ("alikhanifard2024astdiff", "doi", "10.1145/3696002", "A novel refactoring and semantic aware abstract syntax tree differencing tool and a benchmark for evaluating the accuracy of diff tools", ["Alikhanifard", "Tsantalis"]),
    ("lin2025codereviewqa", "doi", "10.18653/v1/2025.findings-acl.476", "CodeReviewQA: The code review comprehension assessment for large language models", ["Lin", "Liu", "Gao", "Thongtanunam", "Treude"]),
    # Dataset (DataCite DOI), cited as the external benchmark source; its paper is a preprint and is not cited.
    ("fu2026reviewanchorbench", "datacite", "10.5281/zenodo.22217751", "ReviewAnchorBench: Executable Benchmark and Replication Package", ["Fu"]),
    ("gitlabautoresolve", "page", "https://docs.gitlab.com/user/project/merge_requests/", "become outdated", []),
    ("githubgraphql", "page", "https://docs.github.com/en/graphql/reference/pulls", "isOutdated", []),
]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, kind, ident, title, authors in REFS:
        rec = {"key": key, "kind": kind, "id": ident, "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            if kind == "doi":
                url = f"https://api.crossref.org/works/{ident}"
                raw = fetch(url)
                msg = json.loads(raw)["message"]
                got_title = " ".join(msg.get("title", []))
                got_auth = [a.get("family", "") for a in msg.get("author", [])]
                rec.update(venue=" ".join(msg.get("container-title", [])), year=msg.get("issued", {}).get("date-parts", [[None]])[0][0])
            elif kind == "datacite":
                url = f"https://api.datacite.org/dois/{ident}"
                raw = fetch(url)
                att = json.loads(raw)["data"]["attributes"]
                got_title = " ".join(t["title"] for t in att.get("titles", []))
                got_auth = [c.get("familyName") or c.get("name", "").split(",")[0] for c in att.get("creators", [])]
                rec.update(venue=att.get("publisher"), year=att.get("publicationYear"), version=att.get("version"))
            elif kind == "arxiv":
                url = f"https://export.arxiv.org/api/query?id_list={ident}"
                raw = fetch(url)
                text = raw.decode("utf-8")
                entry = text[text.index("<entry>"):]
                got_title = re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", entry, re.S).group(1)).strip()
                got_auth = [n.split()[-1] for n in re.findall(r"<name>(.*?)</name>", entry)]
                rec.update(published=re.search(r"<published>(.*?)</published>", entry).group(1),
                           comment=(re.search(r"<arxiv:comment[^>]*>(.*?)</arxiv:comment>", entry, re.S) or [None, None])[1])
            else:
                url = ident
                raw = fetch(url)
                got_title, got_auth = "", []
                rec["contains_term"] = title in raw.decode("utf-8", "replace")
            fname = f"{key}.{'json' if kind == 'doi' else 'xml' if kind == 'arxiv' else 'html'}"
            (OUT / fname).write_bytes(raw)
            rec.update(url=url, file=fname, sha256=hashlib.sha256(raw).hexdigest())
            if kind != "page":
                want = words(title)
                rec["title_found"] = got_title
                rec["title_word_overlap"] = round(len(want & words(got_title)) / len(want), 3)
                rec["authors_found"] = got_auth
                rec["authors_missing"] = [a for a in authors if a not in got_auth]
                rec["ok"] = rec["title_word_overlap"] >= 0.9 and not rec["authors_missing"]
            else:
                rec["ok"] = rec["contains_term"]
        except Exception as e:  # recorded, never hidden
            rec.update(ok=False, error=repr(e))
        rows.append(rec)
        print(("ok  " if rec.get("ok") else "FAIL"), key, rec.get("title_found", rec.get("url", "")), rec.get("error", ""))
    (OUT / "summary.json").write_text(json.dumps({"generator": "tools/v11/verify_v11_citations.py", "rows": rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
