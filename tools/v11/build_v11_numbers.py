"""Generate v11 manuscript macros from evidence JSON (no hand-typed numbers).

Run: python -I -B tools/v11/build_v11_numbers.py   (from paper-drafts/)
Writes v11-professor-revision/generated/numbers-v11.tex and a provenance JSON
recording the SHA-256 of every input read.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "v11-professor-revision" / "generated"
inputs: dict[str, str] = {}
macros: list[tuple[str, str]] = []


def load(rel: str):
    path = ROOT / rel
    raw = path.read_bytes()
    inputs[rel] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw.decode("utf-8"))


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}"


def num(n: int) -> str:
    return f"{n:,}"


def m(name: str, value) -> None:
    assert name.isalpha(), name
    value = str(value)
    if re.fullmatch(r"-[0-9][0-9,.]*", value):  # typographic minus, valid in text and math
        value = "\\ensuremath{-}" + value[1:]
    macros.append((name, value))


# WP E: GitHub review-thread outdating (motivation, I2)
e = load("evidence/v11-wpe/review_threads_summary.json")["pooled"]
m("wpeThreads", num(e["outdated"]["denominator"]))
m("wpeOutdated", num(e["outdated"]["count"]))
m("wpeOutdatedPct", pct(e["outdated"]["share"]))
m("wpeOutdatedLo", pct(e["outdated"]["cluster_bootstrap95"]["low"]))
m("wpeOutdatedHi", pct(e["outdated"]["cluster_bootstrap95"]["high"]))
m("wpeNullLinePct", pct(e["outdated_null_line"]["share"]))
m("wpeFollowedPct", pct(e["followed_by_revision"]["share"]))

# WP A: safety/effort metric family (S1, E5, R2, R3). Macro pattern:
# \sm<Bench><Method><Metric><K|N|Pct|Lo|Hi>, e.g. \smRealCasMissPct.
BENCH = {("main", "all"): "Ctl", ("replication", "all"): "Rep", ("real", "all"): "Real",
         ("real", "oss-targeted"): "PubTgt", ("real", "own-targeted"): "IntTgt",
         ("real", "oss-uniform"): "PubUni", ("real", "own-uniform"): "IntUni"}
METHOD = {"cascade": "Cas", "cascade_v1": "Vone", "quote_exact": "Quote", "diff_drift": "Drift",
          "line_number": "Line", "tracker_adapter": "Trk", "calibrated": "Cal"}
METRIC = {"accuracy": "Acc", "placement_accuracy": "Place", "classification_accuracy": "Class",
          "missed": "Miss", "false_recheck": "False", "wrong": "Wrong", "wrong_silent": "Silent",
          "wrong_with_recheck": "WrongFlag", "lost": "Lost", "gone_correct": "Gone"}
sm = load("evidence/v11-wpa/safety-metrics.json")
sm = sm.get("data", sm)
for (bench, sub), bname in BENCH.items():
    for meth, mname in METHOD.items():
        rec = sm[bench][sub].get(meth)
        if rec is None:
            continue
        for key, kname in METRIC.items():
            r = rec.get(key)
            if not isinstance(r, dict) or "k" not in r:
                continue
            base = f"sm{bname}{mname}{kname}"
            m(base + "K", num(r["k"]))
            m(base + "N", num(r["n"]))
            m(base + "Pct", pct(r["rate"]) if r["n"] else "--")
            if r.get("wilson95"):
                m(base + "Lo", pct(r["wilson95"][0]))
                m(base + "Hi", pct(r["wilson95"][1]))

m("smRealTrkExecFail", num(sm["real"]["all"]["tracker_adapter"]["execution_errors"]))

# WP A: anatomy of the real-history missed re-checks (S3, R4)
ea = load("evidence/v11-wpa/error-analysis.json")
ea = ea.get("data", ea)
mg = ea["marginal_groups"]
m("wpaMissTotal", num(ea["missed_n"]))
m("wpaMissCross", num(mg["tier"]["cross_exact"]))
m("wpaMissSame", num(mg["tier"]["same_exact"]))
m("wpaMissEdited", num(mg["cls"]["edited"]))
m("wpaMissGone", num(mg["cls"]["gone"]))
m("wpaMissSingleLine", num(mg["span"]["1"]))
m("wpaMissHorizonOne", num(mg["horizon"]["1"]))
cf = ea["controlled_failure_groups"]["main"]
m("wpaCtlFailWindow", num(cf["local-window similarity"]))
m("wpaCtlFailNorm", num(cf["whitespace normalisation"]))
m("wpaCtlFailCross", num(cf["cross-file ordering"]))
m("wpaCtlFailOther", num(cf["other"]))

# R03 major 7: direction of reference error (tools/v11/audit_reference_direction.py).
rd = load("evidence/v11-wpa/reference-direction.json")["data"]
assert rd["deployed_missed"] == ea["missed_n"]
m("refdirRows", num(rd["rows"]))
m("refdirUnchanged", num(rd["reference_unchanged"]))
m("refdirCertified", num(rd["reference_unchanged_textually_certified"]))
m("refdirChanged", num(rd["reference_changed_or_deleted"]))
m("refdirPaired", num(rd["changed_by_event"]["edited"]))
m("refdirMissAligned", num(rd["deployed_missed_by_event"]["aligned"]))
m("refdirMissPaired", num(rd["deployed_missed_by_event"]["edited"]))
m("refdirMissDeleted", num(rd["deployed_missed_by_event"]["deleted"]))
m("refdirMissPct", f"{rd['deployed_missed_pct']:.1f}")
m("refdirBoundPct", f"{rd['adverse_bound_missed_pct']:.1f}")
# R4 critic C2: can the relocation step hide a change? (tools/v11/audit_reference_copies.py)
rc = load("evidence/v11-wpa/reference-relocated-copies.json")["data"]
assert rc["reference_unchanged"] == rd["reference_unchanged"] and rc["deployed_missed"] == rd["deployed_missed"]
m("refcopyAligned", num(rc["unchanged_by_event"]["aligned"]))
m("refcopyPaired", num(rc["unchanged_by_event"]["edited"]))
m("refcopyRelocated", num(rc["relocated"]))
m("refcopyChecked", num(rc["relocated_checked"]))
m("refcopyIntroduced", num(rc["relocated_introduced_by_revision"]))
m("refcopySuspect", num(rc["relocated_copy_already_at_reference"]))
m("refcopySuspectSilent", num(rc["suspects_without_deployed_request"]))
m("refcopyUnavailable", num(rc["relocated_unavailable"]))
m("refcopyMissPctChecked", f"{rc['missed_pct_if_checked_suspects_are_changes']:.1f}")
m("refcopyMissPctWorst", f"{rc['missed_pct_if_all_unverified_are_changes']:.1f}")

# WP D: state contract (RQ5). Macros and tables are generated by build_wpd_tex.py from
# evidence/v11-wpd; they are re-emitted here and the tables copied, with input hashes.
OUT.mkdir(parents=True, exist_ok=True)
wpd = load("evidence/v11-wpd/tex/provenance.json")
for k, v in wpd["macros"].items():
    m(k, v)
for name in ("table-transitions.tex", "table-scenarios.tex"):
    rel = f"evidence/v11-wpd/tex/{name}"
    raw = (ROOT / rel).read_bytes()
    inputs[rel] = hashlib.sha256(raw).hexdigest()
    (OUT / name).write_bytes(raw)

# WP B2: compound edits, prefixes, multi-anchor issues, scale (RQ4). Generated by analyze_wpb2.py.
wpb2 = load("evidence/v11-wpb2/tex/provenance.json")
for k, v in wpb2["macros"].items():
    m(k, v)
for rel, name in (("evidence/v11-wpb2/tex/table-compound.tex", "table-compound.tex"),
                  ("evidence/v11-wpb2/figures/compound-v11.pdf", "compound-v11.pdf"),
                  ("evidence/v11-wpb2/figures/chains-v11.pdf", "chains-v11.pdf")):
    raw = (ROOT / rel).read_bytes()
    inputs[rel] = hashlib.sha256(raw).hexdigest()
    (OUT / name).write_bytes(raw)

# WP H2: student-authored repositories (RQ1, held out). Generated by build_wph2_tex.py.
wph2 = load("evidence/v11-wph2/tex/provenance.json")
for k, v in wph2["macros"].items():
    m(k, v)
raw = (ROOT / "evidence/v11-wph2/tex/table-student.tex").read_bytes()
inputs["evidence/v11-wph2/tex/table-student.tex"] = hashlib.sha256(raw).hexdigest()
(OUT / "table-student.tex").write_bytes(raw)

# WP C: external human-annotated benchmark (RQ1). Generated by build_wpc_v11_tex.py from frozen WP C summaries.
wpc = load("evidence/v11-wpc/tex-v11/provenance.json")
for k, v in wpc["macros"].items():
    m(k, v)
raw = (ROOT / "evidence/v11-wpc/tex-v11/table-external.tex").read_bytes()
inputs["evidence/v11-wpc/tex-v11/table-external.tex"] = hashlib.sha256(raw).hexdigest()
(OUT / "table-external.tex").write_bytes(raw)

# WP A / B1 macro files generated by their own builders; re-emitted verbatim (with hashes).
import re as _re
_NEWCMD = _re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}")
for rel in ("evidence/v11-wpa/tex/numbers-wpa.tex", "evidence/v11-wpb1/tex/numbers-wpb.tex"):
    raw = (ROOT / rel).read_bytes()
    inputs[rel] = hashlib.sha256(raw).hexdigest()
    for k, v in _NEWCMD.findall(raw.decode("utf-8")):
        m(k, v)


def signed(x: float, nd: int = 2) -> str:
    """Percentage-point value with a typographic minus for negatives."""
    s = f"{100 * x:.{nd}f}"
    return "\\ensuremath{-}" + s[1:] if s.startswith("-") else s


def pooled(recs, key):
    k = sum(r[key]["k"] for r in recs)
    n = sum(r[key]["n"] for r in recs)
    return k, n


# V11-MACRO-SPEC: WP A values quoted in the design results (definitions follow build_wpa_results.py).
sm_ = load("evidence/v11-wpa/safety-metrics.json")
sm_ = sm_.get("data", sm_)
CHANGED_OPS = ("op-edit_token", "op-insert_and_edit", "op-rewrite", "op-delete_block")
k, n = pooled([sm_["main"][op]["cascade"] for op in CHANGED_OPS], "accuracy")
m("ctlChangedAccPct", pct(k / n))

na = load("evidence/v11-wpa/numerical-audit.json")
na = na.get("data", na)
THETA_WORD = {0.5: "Fifty", 0.7: "Seventy", 0.85: "EightyFive", 0.95: "NinetyFive"}
for row in na["threshold_reviewer_checks"]:
    word = THETA_WORD[row["theta"]]
    m("thetaEdited" + word, pct(row["classes"]["edited"]["rate"]))
    m("thetaGone" + word, pct(row["classes"]["gone"]["rate"]))

fs = load("evidence/v11-wpa/factorial-summary.json")
fs = fs.get("data", fs)
for grp, tag in (("own", "Int"), ("oss", "Pub")):
    eff = fs["real"][grp]["averaged_main_effects"]
    m("wpaScopeGone" + tag, f"{-100 * eff['whole_minus_local']['gone_correct']:.2f}")
    m("wpaOrderMiss" + tag, f"{100 * eff['cross_first_minus_fuzzy_first']['missed']:.2f}")

cu = load("evidence/v11-wpa/cluster-uncertainty.json")
cu = cu.get("data", cu)
eq = cu["real"]["own-targeted"]["repo"]["contrasts"]["final_theta075-minus-cascade_v1"]
m("wpaEqThrDiff", signed(eq["difference"]))
m("wpaEqThrLo", signed(eq["cluster95"][0]))
m("wpaEqThrHi", signed(eq["cluster95"][1]))

cal = load("evidence/v11-wpa/calibration.json")
cal = cal.get("data", cal)
picks = {}
for objective, by_search in cal["selected_theta_counts"].items():
    for search, counts in by_search.items():
        assert len(counts) == 1, (objective, search, counts)
        picks[(objective, search)] = next(iter(counts.items()))
assert len(set(picks.values())) == 1, picks  # same theta, same fold count everywhere
theta, folds = next(iter(picks.values()))
m("wpaLopoTheta", f"{float(theta):.2f}")
m("wpaLopoFolds", num(folds))

ia = load("evidence/v11-wpa/interpretation-audit.json")
ia = ia.get("data", ia)
ref = ia["refined_public_targeted_cell"]
assert (ref["order"], ref["scope"], ref["height"], ref["theta"]) == ("fuzzy_first", "local", "full", float(theta))
m("smPubTgtLopoAccK", num(ref["metrics"]["accuracy"]["k"]))
m("smPubTgtLopoAccN", num(ref["metrics"]["accuracy"]["n"]))
m("smPubTgtLopoAccPct", pct(ref["metrics"]["accuracy"]["rate"]))
feasible = [a for a in cal["safety_constrained"] if a["feasible"]]
m("wpaConstrFeasible", num(len(feasible)))
m("wpaConstrInfeasible", num(len(cal["safety_constrained"]) - len(feasible)))
m("wpaConstrViolate", num(len(ia["public_safety_constraint_violations"])))
ex = next(v for v in feasible if v["design"] == "threshold_only" and v["alpha"] == .01 and v["beta"] == .2)
m("wpaConstrTheta", f"{ex['selected_cell'][3]:.2f}")
m("wpaConstrPubGonePresent", pct(ex["public_evaluation"]["targeted"]["gone_misreported"]["rate"]))

eh = load("evidence/v11-wpa/exclusion-horizon.json")
eh = eh.get("data", eh)
m("wpaExclDiffMedian", f"{eh['distribution']['excluded']['continuous']['diff_size']['quantiles'][2]:g}")
m("wpaRetainedDiffMedian", f"{eh['distribution']['retained']['continuous']['diff_size']['quantiles'][2]:g}")

# V11-MACRO-SPEC: WP B1 held-out stress values (seed 2) and guard costs.
ev = load("evidence/v11-wpb1/evaluation-summary-corrected.json")
ev = ev.get("data", ev)
S = ev["strata"]
ind = S["indentation"]
m("bIndentSemanticN", num(ind["denominators"]["changed"]))
m("bIndentMissDeployed", num(ind["methods"]["t0.85-deployed"]["missed"]["k"]))
m("bIndentMissIG", num(ind["methods"]["t0.85-IG"]["missed"]["k"]))
m("bIndentLayoutN", num(ind["denominators"]["preserved"]))
m("bIndentFalseIG", num(ind["methods"]["t0.85-IG"]["false_recheck"]["k"]))
for meth, tag in (("t0.85-deployed", "Deployed"), ("t0.85-AG", "AG")):
    m("bDupMiss" + tag, pct(S["duplicates"]["methods"][meth]["missed"]["rate"]))
    m("bDupSilent" + tag, pct(S["duplicates"]["methods"][meth]["wrong_silent"]["rate"]))
m("bShortMissDeployed", pct(S["short"]["methods"]["t0.85-deployed"]["missed"]["rate"]))
pub = S["real:oss:targeted"]
m("bVWPubTgtAcc", pct(pub["methods"]["t0.85-VW"]["accuracy"]["rate"]))
for meth, tag in (("t0.85-deployed", "Deployed"), ("t0.85-VW", "VW")):
    m(f"bRange{tag}PubTgt", pct(pub["methods"][meth]["event_counts"]["range_correct"] / pub["denominators"]["range_eligible"]))
ho = load("evidence/v11-wpb1/handoff-numbers.json")
ho = ho.get("data", ho)
arch = ho["archived_safety"]
m("bArchivedMissAG", num(arch["t0.85-AG"]["missed_remaining"]))
m("bArchivedMissAllCal", num(arch["t0.55-IG+AG+VW"]["missed_remaining"]))
hi = ho["history_indentation"]["deployed_returned_span"]
m("bRealIndentReturned", num(hi["normalized_equal_profile_different"]))
oracle_ast = ho["history_indentation"]["oracle_AST_span"]
m("bRealIndentOracle", num(oracle_ast["normalized_equal_profile_different"]))
co = load("evidence/v11-wpb1/closeout.json")
co = co.get("data", co)
for tag in ("IG", "AG"):
    m(f"b{tag}ExtraReal", f"{co['guard_costs']['real']['0.85'][tag]['extra_per_100']:.2f}")
gc = co["guard_costs"]["real:oss:targeted"]["0.85"]
m("bIGExtraPubTgt", f"{gc['IG']['extra_per_100']:.2f}")
m("bAGExtraPubTgt", f"{gc['AG']['extra_per_100']:.2f}")

lines = ["% Generated by tools/v11/build_v11_numbers.py; do not edit."]
lines += ["\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros]
(OUT / "numbers-v11.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
(OUT / "numbers-v11-provenance.json").write_text(
    json.dumps({"inputs": inputs, "macros": dict(macros)}, indent=2), encoding="utf-8")
print(f"{len(macros)} macros from {len(inputs)} inputs")
