#!/usr/bin/env python3
"""Collect public GitHub PR review-thread snapshots and aggregate I2 metrics.

Raw JSON contains only requested public fields; author identities and comment text
are never queried or written. Collection uses ``gh api graphql`` for auth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "v11-wpe"
RAW = EVIDENCE / "raw"
REPOS = ["psf/requests", "pallets/flask", "pallets/click", "encode/httpx", "Textualize/rich"]
START, END = "2022-01-01", "2026-06-30"
CAP, SEED, BOOTSTRAPS = 400, 20261031, 10000
DOCS_URL = "https://docs.github.com/en/graphql/reference/objects#reviewthread"

SEARCH = """query($q:String!,$cursor:String){search(query:$q,type:ISSUE,first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{... on PullRequest{number createdAt mergedAt reviewThreads(first:1){totalCount} commits(first:1){totalCount}}}}}"""
THREADS = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{isOutdated isResolved path line originalLine comments(first:1){totalCount nodes{createdAt}}}}}}}"""
COMMITS = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){pullRequest(number:$number){commits(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{commit{committedDate}}}}}}"""


def gh(query: str, variables: dict, label: str) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, val in variables.items():
        args += ["-F", f"{key}={val}" if val is not None else f"{key}=null"]
    delay = 2
    for attempt in range(8):
        p = subprocess.run(args, text=True, capture_output=True)
        if p.returncode == 0:
            try:
                obj = json.loads(p.stdout)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid GraphQL JSON ({label}): {e}") from e
            if not obj.get("errors"):
                return obj["data"]
            msg = json.dumps(obj["errors"])
        else:
            msg = p.stderr.strip()
        transient = any(s in msg.lower() for s in ("rate limit", "secondary rate", "abuse", "502", "503", "timeout"))
        if not transient or attempt == 7:
            raise RuntimeError(f"GitHub GraphQL failed ({label}): {msg[:800]}")
        wait = min(300, delay)
        print(f"Transient/rate response for {label}; waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
        delay = min(300, delay * 2)
    raise AssertionError("unreachable")


def dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect() -> None:
    for repo in REPOS:
        owner, name = repo.split("/")
        print(f"Searching {repo}", flush=True)
        q = f"repo:{repo} is:pr is:merged merged:{START}..{END}"
        cursor, candidates = None, []
        page = 0
        while True:
            data = gh(SEARCH, {"q": q, "cursor": cursor}, f"{repo} search page {page+1}")["search"]
            dump(RAW / repo.replace("/", "__") / f"search-{page+1:03d}.json", data)
            candidates.extend(n for n in data["nodes"] if n and n.get("mergedAt"))
            page += 1
            if not data["pageInfo"]["hasNextPage"]:
                break
            cursor = data["pageInfo"]["endCursor"]
            time.sleep(1)
        candidates.sort(key=lambda x: (x["mergedAt"], x["number"]), reverse=True)
        included, eligible = [], []
        for pr in candidates:
            if (pr["mergedAt"][:10] < START or pr["mergedAt"][:10] > END or
                    not pr.get("reviewThreads", {}).get("totalCount", 0)):
                continue
            eligible.append(pr)
            if len(included) < CAP:
                included.append(pr)
        for idx, pr in enumerate(included, 1):
            number = pr["number"]
            base = RAW / repo.replace("/", "__") / f"pr-{number}"
            print(f"  {repo} PR #{number} ({idx}/{len(included)})", flush=True)
            threads, commits = [], []
            cursor = None
            pg = 0
            while True:
                obj = gh(THREADS, {"owner": owner, "name": name, "number": number, "cursor": cursor}, f"{repo} PR {number} threads {pg+1}")["repository"]["pullRequest"]["reviewThreads"]
                dump(base / f"threads-{pg+1:03d}.json", obj)
                threads.extend(obj["nodes"])
                pg += 1
                if not obj["pageInfo"]["hasNextPage"]: break
                cursor = obj["pageInfo"]["endCursor"]
                time.sleep(0.5)
            cursor = None
            pg = 0
            while True:
                obj = gh(COMMITS, {"owner": owner, "name": name, "number": number, "cursor": cursor}, f"{repo} PR {number} commits {pg+1}")["repository"]["pullRequest"]["commits"]
                dump(base / f"commits-{pg+1:03d}.json", obj)
                commits.extend(x["commit"]["committedDate"] for x in obj["nodes"])
                pg += 1
                if not obj["pageInfo"]["hasNextPage"]: break
                cursor = obj["pageInfo"]["endCursor"]
                time.sleep(0.5)
            # Aggregation input is compacted into an additional raw snapshot. No logins/text.
            compact = {"repository": repo, "number": number, "createdAt": pr["createdAt"], "mergedAt": pr["mergedAt"], "committedDates": commits, "threads": threads}
            dump(base / "record.json", compact)
            time.sleep(1)
        dump(RAW / repo.replace("/", "__") / "collection.json", {
            "repository": repo, "query": q, "candidateMergedPRsInWindow": len(candidates),
            "qualifyingPRsWithInlineThreads": len(eligible), "includedPRs": len(included),
            "cappedAt400": len(eligible) > CAP, "selection": "most recently merged qualifying PRs",
            "collectionDate": datetime.now(timezone.utc).date().isoformat(),
            "searchResultCount": len(candidates),
        })


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if not n: return {"low": None, "high": None}
    p = k / n
    den = 1 + z*z/n
    ctr = (p + z*z/(2*n)) / den
    rad = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return {"low": ctr-rad, "high": ctr+rad}


def records():
    out = []
    for path in sorted(RAW.glob("*/pr-*/record.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def stats(group):
    threads = [t for r in group for t in r["threads"]]
    followed = []
    outdated = [t for t in threads if t["isOutdated"]]
    for r in group:
        dates = sorted(r["committedDates"])
        for t in r["threads"]:
            dt = t["comments"]["nodes"][0]["createdAt"] if t["comments"]["nodes"] else None
            is_followed = bool(dt and any(c > dt for c in dates))
            if is_followed: followed.append(t)
            t["_followed"] = is_followed
    rounds, after = 0, []
    for r in group:
        dates = sorted(r["committedDates"])
        firsts = [t["comments"]["nodes"][0]["createdAt"] for t in r["threads"] if t["comments"]["nodes"]]
        if firsts:
            first = min(firsts)
            n_after = sum(c > first for c in dates)
            after.append(n_after)
            rounds += n_after >= 1
    def metric(k,n): return {"count":k,"denominator":n,"share":(k/n if n else None),"wilson95":wilson(k,n)}
    resolved = sum(t["isResolved"] for t in outdated)
    null_line = sum(t["line"] is None for t in outdated)
    return {
        "thread_count": len(threads), "pr_count": len(group),
        "outdated": metric(len(outdated),len(threads)),
        "followed_by_revision": metric(len(followed),len(threads)),
        "outdated_among_followed": metric(sum(t["isOutdated"] for t in followed),len(followed)),
        "outdated_resolved": metric(resolved,len(outdated)),
        "outdated_unresolved": metric(len(outdated)-resolved,len(outdated)),
        "prs_with_revision_after_first_thread": metric(rounds,len(after)),
        "median_commits_after_first_thread": (lambda xs: (xs[(len(xs)-1)//2] + xs[len(xs)//2]) / 2)(sorted(after)) if after else None,
        "outdated_null_line": metric(null_line,len(outdated)),
        "outdated_still_placed": metric(len(outdated)-null_line,len(outdated)),
    }


def cluster_bootstrap(groups):
    rng = random.Random(SEED)
    pr_groups = [r for r in groups]
    names = list(pr_groups)
    # Each resample draws PR clusters with replacement and recomputes pooled ratios.
    rows = {k: [] for k in ("outdated", "followed_by_revision", "outdated_among_followed", "outdated_resolved", "outdated_unresolved", "prs_with_revision_after_first_thread", "outdated_null_line", "outdated_still_placed")}
    for _ in range(BOOTSTRAPS):
        sample = [pr_groups[rng.randrange(len(pr_groups))] for _ in names]
        s = stats(sample)
        for key in rows:
            rows[key].append(s[key]["share"])
    result = {}
    for key, vals in rows.items():
        vals = sorted(v for v in vals if v is not None)
        result[key] = {"low": vals[int(.025*(len(vals)-1))], "high": vals[int(.975*(len(vals)-1))]}
    return result


def tex_macro(name, value):
    return f"\\newcommand{{\\{name}}}{{{value}}}\n"


def aggregate():
    all_records = records()
    if not all_records: raise SystemExit("No cached PR record.json files found")
    grouped = {repo: [r for r in all_records if r["repository"] == repo] for repo in REPOS}
    result = {"collection_date": None, "query": {"search_filter": f"repo:<owner>/<name> is:pr is:merged merged:{START}..{END}", "population": "merged PRs with at least one inline review thread", "fields": ["number", "createdAt", "mergedAt", "commits.commit.committedDate", "reviewThreads.isOutdated", "reviewThreads.isResolved", "reviewThreads.path", "reviewThreads.line", "reviewThreads.originalLine", "reviewThreads.comments.totalCount", "reviewThreads.comments.nodes.createdAt"], "selection_if_over_cap": f"400 PRs with the latest mergedAt per repository"}, "repositories": {}, "pooled": {}, "method": {"wilson_confidence": .95, "pooled_cluster_bootstrap_resamples": BOOTSTRAPS, "seed": SEED, "bootstrap_unit": "PR", "bootstrap_interval": "percentile 95%", "collection_snapshot": "GitHub state at collection date"}, "raw_files_sha256": {}}
    for repo, group in grouped.items():
        coll = RAW / repo.replace("/", "__") / "collection.json"
        info = json.loads(coll.read_text(encoding="utf-8")) if coll.exists() else {}
        count_file = RAW / repo.replace("/", "__") / "search-count.json"
        if count_file.exists():
            count_data = json.loads(count_file.read_text(encoding="utf-8"))
            info["githubSearchIssueCount"] = count_data["data"]["search"]["issueCount"]
            info["candidateCountMatchesSearchCount"] = info.get("candidateMergedPRsInWindow") == info["githubSearchIssueCount"]
        result["repositories"][repo] = {"sampling": info, "metrics": stats(group)}
    result["collection_date"] = max((x["sampling"].get("collectionDate", "") for x in result["repositories"].values()), default=None) or None
    pooled = stats(all_records)
    bootstrap = cluster_bootstrap(all_records)
    for key, interval in bootstrap.items():
        pooled[key]["cluster_bootstrap95"] = interval
    result["pooled"] = pooled
    for f in sorted(RAW.rglob("*.json")):
        result["raw_files_sha256"][str(f.relative_to(EVIDENCE)).replace("\\", "/")] = hashlib.sha256(f.read_bytes()).hexdigest()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    dump(EVIDENCE / "review_threads_summary.json", result)
    tex = EVIDENCE / "tex" / "review_threads_macros.tex"
    tex.parent.mkdir(parents=True, exist_ok=True)
    p = pooled
    def pct(key): return f"{100*p[key]['share']:.1f}\\%" if p[key]["share"] is not None else "NA"
    content = "".join([
        tex_macro("wpeOutdatedPct", pct("outdated")),
        tex_macro("wpeFollowedPct", pct("followed_by_revision")),
        tex_macro("wpeFollowedOutdatedPct", pct("outdated_among_followed")),
        tex_macro("wpeOutdatedResolvedPct", pct("outdated_resolved")),
        tex_macro("wpeOutdatedUnresolvedPct", pct("outdated_unresolved")),
        tex_macro("wpeMultiRoundPRPct", pct("prs_with_revision_after_first_thread")),
        tex_macro("wpeMedianCommitsAfterFirstThread", str(int(p["median_commits_after_first_thread"])) if p["median_commits_after_first_thread"] == int(p["median_commits_after_first_thread"]) else str(p["median_commits_after_first_thread"])),
        tex_macro("wpeOutdatedNullLinePct", pct("outdated_null_line")),
        tex_macro("wpeOutdatedPlacedPct", pct("outdated_still_placed")),
    ])
    tex.write_text(content, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true", help="fetch public data using authenticated gh CLI")
    ap.add_argument("--aggregate", action="store_true", help="aggregate cached raw JSON deterministically")
    args = ap.parse_args()
    if args.collect: collect()
    if args.aggregate or not args.collect: aggregate()


if __name__ == "__main__": main()
