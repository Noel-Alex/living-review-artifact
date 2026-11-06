#!/usr/bin/env python3
"""Frozen H1 GitHub repository discovery. Uses gh auth, read-only API, and local metric clones."""
from __future__ import annotations
import argparse, base64, datetime as dt, json, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "v11-wph"
PRIVATE = EVIDENCE / "private"
TMP = PRIVATE / "tmp"
PROTOCOL = ROOT / "review" / "V11-PROTOCOL-H.md"
FREEZE = EVIDENCE / "protocol-freeze.json"
API = "https://api.github.com"
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
CUTOFF = dt.date(2022, 11, 30)
CREATED_FROM = dt.date(2016, 1, 1)
CREATED_TO = dt.date(2022, 11, 29)
MIN_LOC, MIN_COMMITS, MIN_AUTHORS = 2000, 60, 2
MIN_PRE_SHARE = .90
QUERIES = [
    "capstone language:python created:2016-01-01..2022-11-29",
    '"final year project" language:python created:2016-01-01..2022-11-29',
    '"senior design" language:python created:2016-01-01..2022-11-29',
    '"course project" language:python created:2016-01-01..2022-11-29',
    '"semester project" language:python created:2016-01-01..2022-11-29',
    '"capstone project" language:python created:2016-01-01..2022-11-29',
    '"final year" "course project" language:python created:2016-01-01..2022-11-29',
    '"senior project" university language:python created:2016-01-01..2022-11-29',
]
EVIDENCE_RE = re.compile(r"\b(capstone(?:\s+project)?|final[- ]year\s+project|senior\s+design|course\s+project|semester\s+project|(?:CS|CSE|ECE|EE|ME|IT|MCA|BCA|ENGR|COMP)\s*[-.]?\s*\d{2,4}|(?:university|college|institute|school)\s+of\s+[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,5})\b", re.I)
CATEGORY_RE = [
    ("capstone", re.compile(r"\bcapstone(?:\s+project)?\b", re.I)),
    ("final_year_project", re.compile(r"\bfinal[- ]year\s+project\b", re.I)),
    ("senior_design", re.compile(r"\bsenior\s+design\b", re.I)),
    ("course_project", re.compile(r"\bcourse\s+project\b", re.I)),
    ("semester_project", re.compile(r"\bsemester\s+project\b", re.I)),
    ("course_code", re.compile(r"\b(?:CS|CSE|ECE|EE|ME|IT|MCA|BCA|ENGR|COMP)\s*[-.]?\s*\d{2,4}\b", re.I)),
    ("institution_name", re.compile(r"\b(?:university|college|institute|school)\s+of\s+[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,5}\b")),
]
VENDOR_COMPONENTS = {"vendor", "vendors", "third_party", "third-party", "thirdparty", "external", "externals", "deps", "dependencies", "site-packages", "bower_components", "node_modules", "lib_external"}
VENDOR_FILES = ("_vendor.py",)
AUTHORED_TUTORIAL_RE = re.compile(r"(?:\b(?:instructor|lecturer|professor|teacher|faculty)\b.{0,100}\b(?:author|maintain|created|course material|teaching material|tutorial)|\b(?:course|teaching)\s+materials?\b.{0,100}\b(?:by|authored|maintained)\s+(?:the\s+)?(?:instructor|lecturer|professor|teacher|faculty))", re.I | re.S)
TEMPLATE_RE = re.compile(r"(?:\b(?:fork|mirror|copy|template|boilerplate|starter\s+(?:code|repository|repo))\b.{0,100}\b(?:template|starter|course|project|repository|repo)|\b(?:fork|mirror)\s+of\b)", re.I | re.S)


def run(args, cwd=None, check=True, capture=True):
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {args[0]} {args[1] if len(args)>1 else ''}: {(p.stderr or '')[-500:]}")
    return p.stdout.strip() if capture else ""


def gh_api(path, raw=False):
    req = urllib.request.Request(f"{API}/{path}", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Vcap-WPH1-discovery"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def readme_text(full_name):
    try:
        raw = gh_api(f"repos/{full_name}/readme")
        obj = json.loads(raw)
        return base64.b64decode(obj.get("content", "")).decode("utf-8", "replace")
    except Exception:
        try:
            return gh_api(f"repos/{full_name}/readme", raw=True)
        except Exception:
            return ""


def gh_search(query, query_record):
    gathered, total, pages = [], None, 0
    for page in range(1, 11):
        encoded = urllib.parse.quote(query, safe="")
        print(f"search query {len(query_record)+1}/{len(QUERIES)} page {page}: {query}", flush=True)
        obj = json.loads(gh_api(f"search/repositories?q={encoded}&per_page=100&page={page}"))
        if total is None:
            total = obj.get("total_count", 0)
        items = obj.get("items", [])
        pages += 1
        gathered.extend(items)
        if len(items) < 100 or page * 100 >= min(total or 0, 1000):
            break
        time.sleep(.2)
    query_record.append({"query": query, "reported_total_count": total, "pages_fetched": pages, "results_fetched": len(gathered), "capped_at_1000": bool((total or 0) > 1000)})
    return gathered


def sentence_with_match(text):
    # Preserve line boundaries, then take a sentence or a single README line.
    for raw in text.replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw).strip(" \t-*#>\"'`")
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        sentences, pending = [], ""
        for part in parts:
            if pending and re.search(r"\b(?:Prof|Dr|Mr|Mrs|Ms|St|No|vs|e\.g|i\.e)\.$", pending, re.I):
                pending += " " + part
            else:
                if pending:
                    sentences.append(pending)
                pending = part
        if pending:
            sentences.append(pending)
        for sent in sentences:
            sent = sent.strip()
            m = EVIDENCE_RE.search(sent)
            if m:
                # "Capstone" is also a software/tool name; require an education or
                # project context so a tool description cannot stand in for student work.
                if m.group(0).casefold().startswith("capstone") and not re.search(r"\b(?:capstone\s+project|student|course|class|semester|senior|final[- ]year|university|college|institute|school|CS|CSE|ECE|EE|ME|IT|MCA|BCA|ENGR|COMP)\b", sent, re.I):
                    continue
                if len(sent) > 200:
                    left = max(0, m.start() - 75)
                    prefix = "…" if left else ""
                    sent = prefix + sent[left:left + 199 - len(prefix)] + "…"
                return sent[:200], m.group(0)
    return None, None


def author_evidence(desc, readme):
    for source in (desc or "", readme or ""):
        sentence, matched = sentence_with_match(source)
        if sentence:
            category = next((name for name, rx in CATEGORY_RE if rx.search(sentence)), "institution_name")
            return sentence, category, matched
    return None, None, None


def clone_metrics(repo, rid):
    dest = TMP / str(rid)
    source_dest = TMP / f"{rid}-head"
    if not dest.exists():
        TMP.mkdir(parents=True, exist_ok=True)
        # Full commit graph with filtered blobs keeps commit traversal small.
        run(["git", "clone", "--bare", "--filter=blob:none", f"https://github.com/{repo['full_name']}.git", str(dest)])
    head = run(["git", "--git-dir", str(dest), "rev-parse", "refs/heads/" + repo["default_branch"] + "^{commit}"])
    if not source_dest.exists():
        # A separate shallow, unfiltered head snapshot fetches Python blobs in one pack.
        run(["git", "clone", "--bare", "--depth=1", "--branch", repo["default_branch"], f"https://github.com/{repo['full_name']}.git", str(source_dest)])
    source_head = run(["git", "--git-dir", str(source_dest), "rev-parse", "HEAD^{commit}"])
    if source_head != head:
        raise RuntimeError("repository default branch moved during metric snapshot; rerun to obtain a consistent pin")
    rows = run(["git", "--git-dir", str(dest), "log", "--first-parent", "--format=%aI%x00%an%x00%ae", head]).splitlines()
    authors, before = set(), 0
    for row in rows:
        fields = row.split("\x00")
        if len(fields) < 3:
            continue
        try:
            date = dt.datetime.fromisoformat(fields[0].replace("Z", "+00:00")).date()
            if date < CUTOFF:
                before += 1
        except ValueError:
            pass
        # Only use identities in memory; never write or print them.
        authors.add((fields[1].strip().casefold(), fields[2].strip().casefold()))
    first_parent = len(rows)
    tree = run(["git", "--git-dir", str(dest), "ls-tree", "-r", "--name-only", head]).splitlines()
    pyfiles = [p for p in tree if p.lower().endswith(".py")]
    loc = vendor_loc = 0
    for path in pyfiles:
        try:
            blob = run(["git", "--git-dir", str(source_dest), "show", f"{head}:{path}"])
        except Exception:
            continue
        lines = [ln for ln in blob.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        count = len(lines)
        loc += count
        parts = {x.casefold() for x in pathlib.PurePosixPath(path).parts}
        base = pathlib.PurePosixPath(path).name.casefold()
        if parts & VENDOR_COMPONENTS or base.endswith(VENDOR_FILES):
            vendor_loc += count
    return {"head_sha": head, "first_parent_commits": first_parent, "distinct_first_parent_authors": len(authors), "pre_cutoff_commits": before, "pre_cutoff_share": before / first_parent if first_parent else 0.0, "python_loc": loc, "vendored_python_loc": vendor_loc, "vendored_python_loc_share": vendor_loc / loc if loc else 1.0, "tracked_python_files": len(pyfiles)}


def criterion(result, key, passed, reason=None):
    result["checks"][key] = {"pass": bool(passed), **({"reason": reason} if reason else {})}


def screen(repo):
    full_name, rid = repo["full_name"], repo["id"]
    r = {"repository_id": rid, "full_name": full_name, "checks": {}, "metrics": {}, "selected": False}
    criterion(r, "public_not_fork_not_archived", not repo.get("private", True) and not repo.get("fork", True) and not repo.get("archived", True), "private, fork, or archived" if repo.get("private") or repo.get("fork") or repo.get("archived") else None)
    criterion(r, "primary_language_python", repo.get("language") == "Python", f"primary language: {repo.get('language')}" if repo.get("language") != "Python" else None)
    try:
        created = dt.date.fromisoformat(repo["created_at"][:10])
        dateok = CREATED_FROM <= created <= CREATED_TO
        criterion(r, "created_date", dateok, f"created {created.isoformat()}" if not dateok else None)
        r["metrics"]["created_year"] = created.year
    except Exception as e:
        criterion(r, "created_date", False, f"invalid created_at: {e}")
        created = None
    desc = repo.get("description") or ""
    readme = readme_text(full_name)
    ev, category, matched = author_evidence(desc, readme)
    criterion(r, "student_authorship_evidence", ev is not None, "no qualifying README/description sentence" if not ev else None)
    r["metrics"]["evidence_string"] = ev
    r["metrics"]["evidence_category"] = category
    # Exclusions use explicit contextual patterns, not isolated generic words.
    combined = desc + "\n" + readme[:200000]
    tutorial = bool(AUTHORED_TUTORIAL_RE.search(combined))
    template = bool(TEMPLATE_RE.search(combined)) or bool(repo.get("fork"))
    criterion(r, "not_instructor_tutorial_or_course_material", not tutorial, "authorship/context marker" if tutorial else None)
    criterion(r, "not_template_fork_or_mirror", not template, "template/starter/mirror context marker" if template else None)
    try:
        metrics = clone_metrics(repo, rid)
        r["metrics"].update(metrics)
        criterion(r, "not_notebooks_only", metrics["tracked_python_files"] > 0, "no tracked .py files at head" if metrics["tracked_python_files"] == 0 else None)
        criterion(r, "python_loc_at_least_2000", metrics["python_loc"] >= MIN_LOC, f"{metrics['python_loc']} Python LOC")
        criterion(r, "first_parent_commits_at_least_60", metrics["first_parent_commits"] >= MIN_COMMITS, f"{metrics['first_parent_commits']} first-parent commits")
        criterion(r, "at_least_two_distinct_authors", metrics["distinct_first_parent_authors"] >= MIN_AUTHORS, f"{metrics['distinct_first_parent_authors']} distinct authors")
        criterion(r, "pre_cutoff_share_at_least_90_percent", metrics["pre_cutoff_share"] >= MIN_PRE_SHARE, f"share {metrics['pre_cutoff_share']:.6f}")
        criterion(r, "vendored_python_share_at_most_50_percent", metrics["vendored_python_loc_share"] <= .5, f"share {metrics['vendored_python_loc_share']:.6f}")
    except Exception as e:
        r["metrics"]["metric_error"] = str(e)[:500]
        for key in ("not_notebooks_only", "python_loc_at_least_2000", "first_parent_commits_at_least_60", "at_least_two_distinct_authors", "pre_cutoff_share_at_least_90_percent", "vendored_python_share_at_most_50_percent"):
            criterion(r, key, False, "metric unavailable: clone/API error")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-selected", type=int, default=20)
    ap.add_argument("--resume", action="store_true", help="reuse prior private screening records and existing bare clones")
    args = ap.parse_args()
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    actual = __import__("hashlib").sha256(PROTOCOL.read_bytes()).hexdigest()
    if actual != frozen["sha256"]:
        raise SystemExit("protocol hash mismatch; refusing discovery")
    query_records, by_id = [], {}
    cache_dir = PRIVATE / "search-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for qi, q in enumerate(QUERIES, 1):
        cache_file = cache_dir / f"query-{qi:02d}.json"
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            query_records.append(cached["record"])
            results = cached["items"]
        else:
            before = len(query_records)
            results = gh_search(q, query_records)
            cache_file.write_text(json.dumps({"record": query_records[before], "items": results}, indent=2)+"\n", encoding="utf-8")
        for obj in results:
            by_id[obj["id"]] = obj
        time.sleep(.5)
    candidates = sorted(by_id.values(), key=lambda x: x["id"])
    audit_path = PRIVATE / "screened.json"
    prior = {}
    if args.resume and audit_path.exists():
        prior = {x["repository_id"]: x for x in json.loads(audit_path.read_text(encoding="utf-8"))["screened"]}
    screened, selected = [], []
    for repo in candidates:
        rec = prior.get(repo["id"]) or screen(repo)
        screened.append(rec)
        if all(x["pass"] for x in rec["checks"].values()):
            rec["selected"] = True
            selected.append(rec)
            if len(selected) >= args.max_selected:
                break
        if len(screened) % 10 == 0:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps({"screened": screened, "query_results": query_records}, indent=2)+"\n", encoding="utf-8")
            print(f"screened={len(screened)} passing={len(selected)}", flush=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps({"screened": screened, "query_results": query_records, "candidate_count": len(candidates), "query_cap_may_truncate": any(x["capped_at_1000"] for x in query_records)}, indent=2)+"\n", encoding="utf-8")
    selected_output = []
    for i, rec in enumerate(selected, 1):
        m = rec["metrics"]
        selected_output.append({"repository_id": rec["repository_id"], "full_name": rec["full_name"], "default_branch": by_id[rec["repository_id"]]["default_branch"], "head_commit_sha": m["head_sha"], "evidence_string": m["evidence_string"], "evidence_category": m["evidence_category"], "metrics": {k:v for k,v in m.items() if k != "evidence_string" and k != "evidence_category"}, "anonymous_id": f"S{i}"})
    (EVIDENCE / "private").mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "private" / "selected.json").write_text(json.dumps(selected_output, indent=2)+"\n", encoding="utf-8")
    criterion_keys = ("public_not_fork_not_archived", "primary_language_python", "created_date", "student_authorship_evidence", "not_instructor_tutorial_or_course_material", "not_template_fork_or_mirror", "not_notebooks_only", "python_loc_at_least_2000", "first_parent_commits_at_least_60", "at_least_two_distinct_authors", "pre_cutoff_share_at_least_90_percent", "vendored_python_share_at_most_50_percent")
    rejects = {key: 0 for key in criterion_keys}
    for rec in screened:
        for key, check in rec["checks"].items():
            if not check["pass"]:
                rejects[key] = rejects.get(key, 0) + 1
    summary = {"query_count": len(query_records), "queries": query_records, "unique_candidate_count": len(candidates), "screened_count": len(screened), "selected_count": len(selected_output), "rejected_per_criterion_nonexclusive": rejects, "selection_rule": "ascending numeric GitHub repository id; first passing repositories", "query_cap_may_truncate": any(x["capped_at_1000"] for x in query_records)}
    (EVIDENCE / "screening_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"candidate_count": len(candidates), "screened_count": len(screened), "selected_count": len(selected_output), "rejected_per_criterion": rejects, "query_cap_may_truncate": summary["query_cap_may_truncate"]}, indent=2))

if __name__ == "__main__":
    main()
