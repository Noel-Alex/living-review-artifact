"""Generate WP I manuscript macros and tables from the latest evidence/v11-wpi/summary-*.json.

Run: python -I -B tools/v11/build_wpi_tex.py   (from paper-drafts/)
Writes v11-professor-revision/generated/numbers-wpi.tex, table-locator.tex, table-identity.tex
and numbers-wpi-provenance.json. Macro pattern: \\wi<Pop><Method><Metric>[K|N] (rate in percent).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / 'evidence/v11-wpi'
OUT = ROOT / 'v11-professor-revision' / 'generated'
POPS = {'fresh:indentation': 'FrInd', 'fresh:duplicates': 'FrDup', 'fresh:short': 'FrShort', 'fresh:compound': 'FrCmp',
        'fresh:compound:k=1': 'FrCmpOne', 'fresh:compound:k=4': 'FrCmpFour', 'fresh': 'Fr',
        'stress:indentation': 'StInd', 'stress:duplicates': 'StDup', 'stress:short': 'StShort',
        'controlled:replication': 'Ctl', 'compound': 'Cmp', 'compound:k=1': 'CmpOne', 'compound:k=4': 'CmpFour',
        'real': 'Real', 'real:oss:targeted': 'PubTgt', 'students': 'Stu', 'students:targeted': 'StuTgt',
        'external': 'Ext', 'external:human-AB': 'Hum', 'external:human-AB:non-Python-code': 'HumNp'}
METHODS = {'t0.85-deployed': 'Dep',  # equals deployed_native wherever both exist; defined on every population
           't0.85-AG': 'CasAG', 't0.85-AG2': 'CasAGtwo',
           't0.85-IG+AG+VW': 'CasG', 't0.85-IG+AG2+VW': 'CasGtwo', 't0.55-IG+AG+VW': 'CalG', 't0.55-IG+AG2+VW': 'CalGtwo',
           'codemapper+quote': 'CmQ', 'codemapper+IG': 'CmIG', 'codemapper+AG': 'CmAG', 'codemapper+AG2': 'CmAGtwo',
           'codemapper+IG+AG': 'CmG', 'codemapper+IG+AG2': 'CmGtwo',
           'cmhybrid+quote': 'ChQ', 'cmhybrid+AG2': 'ChAGtwo', 'cmhybrid+IG+AG2': 'ChGtwo',
           'tracker+quote': 'TrQ', 'tracker+IG+AG': 'TrG', 'tracker+IG+AG2': 'TrGtwo',
           'gumtree+quote': 'GtQ', 'gumtree+IG+AG': 'GtG', 'gumtree+IG+AG2': 'GtGtwo',
           'hybrid+quote': 'HyQ', 'hybrid+IG+AG': 'HyG', 'hybrid+IG+AG2': 'HyGtwo',
           't0.85-AGi': 'CasAGi', 't0.85-IG+AGi+VW': 'CasGi', 't0.55-IG+AGi+VW': 'CalGi', 't0.85-IG+AG': 'CasIGAG',
           'codemapper+AGi': 'CmAGi', 'codemapper+IG+AGi': 'CmGi', 'cmhybrid+IG+AGi': 'ChGi',
           'tracker+IG+AGi': 'TrGi', 'gumtree+IG+AGi': 'GtGi', 'hybrid+IG+AGi': 'HyGi'}
METRICS = {'accuracy': 'Acc', 'placement_accuracy': 'Place', 'missed': 'Miss', 'false_recheck': 'False',
           'wrong_silent': 'Silent', 'wrong': 'Wrong', 'lost': 'Lost', 'range_correct': 'Range',
           'wrong_with_recheck': 'Misdir'}
macros: list[tuple[str, str]] = []


def m(name, value):
    assert re.fullmatch(r'[A-Za-z]+', name), name
    value = str(value)
    if re.fullmatch(r'-[0-9][0-9,.]*', value):
        value = '\\ensuremath{-}' + value[1:]
    macros.append((name, value))


def pct(r, nd=1):
    return '--' if r is None or r.get('rate') is None else f"{100 * r['rate']:.{nd}f}"


def num(n):
    return f'{n:,}'


def latest():
    files = sorted(EV.glob('summary-*.json'))
    assert files, 'no WP I summary'
    return files[-1]


TABLE_POPS = (('real', 'Real histories'), ('students', 'Student repositories'), ('external:human-AB', 'Human-annotated'),
              ('fresh', 'Held-out stress'))
TABLE_ROWS = (('Cascade', (('t0.85-deployed', 'deployed'), ('t0.85-IG+AGi+VW', '+IG+AGi+VW'), ('t0.55-IG+AGi+VW', '+IG+AGi+VW, $\\theta{=}0.55$'))),
              ('CodeMapper', (('codemapper+quote', 'labels only'), ('codemapper+IG+AG', '+IG+AG'), ('codemapper+IG+AGi', '+IG+AGi'))),
              ('CodeMapper, cross-file fallback', (('cmhybrid+quote', 'labels only'), ('cmhybrid+IG+AGi', '+IG+AGi$^{*}$'))),
              ('Contextual tracker', (('tracker+quote', 'labels only'), ('tracker+IG+AGi', '+IG+AGi'))))
TABLE_METRICS = (('placement_accuracy', 'Place'), ('missed', 'Miss'), ('wrong_silent', 'Silent'), ('wrong_with_recheck', 'Misdir'),
                 ('lost', 'Lost'), ('false_recheck', 'Extra'))
STRESS_POPS = (('fresh:indentation', 'Indentation'), ('fresh:duplicates', 'Duplicate copy'), ('fresh:short', 'Short anchor'),
               ('fresh:compound', 'Compound'))
STRESS_ROWS = (('Cascade', (('t0.85-deployed', 'deployed'), ('t0.85-AG', '+AG'), ('t0.85-AGi', '+AGi'), ('t0.85-AG2', '+AG2'),
                            ('t0.85-IG+AGi+VW', '+IG+AGi+VW'))),
               ('CodeMapper', (('codemapper+quote', 'labels only'), ('codemapper+IG', '+IG'), ('codemapper+AG', '+AG'),
                               ('codemapper+AGi', '+AGi'), ('codemapper+IG+AGi', '+IG+AGi'))))
STRESS_METRICS = (('missed', 'Miss'), ('wrong_silent', 'Silent'), ('false_recheck', 'Extra'))


def stress_table(strata):
    """Held-out stress seed by suite (R03 critic W6): every guard variant on the deployed cascade and on CodeMapper."""
    k = len(STRESS_METRICS)
    out = ['\\begin{table*}[t]', '\\caption{Held-Out Stress Suites by Guard (\\%)}\\label{tab:stress}', '\\centering\\footnotesize',
           '\\setlength{\\tabcolsep}{3pt}', '\\begin{tabular}{@{}l' + ('r' * k + '@{\\hspace{8pt}}') * (len(STRESS_POPS) - 1) + 'r' * k + '@{}}\\toprule']
    out.append(' & ' + ' & '.join(f'\\multicolumn{{{k}}}{{c}}{{{label}}}' for _, label in STRESS_POPS) + ' \\\\')
    out.append(' & ' + ' & '.join(
        f'\\multicolumn{{{k}}}{{c}}{{\\scriptsize {num(strata[p]["methods"]["t0.85-deployed"]["denominators"]["changed"])} / '
        f'{num(strata[p]["methods"]["t0.85-deployed"]["denominators"]["preserved"])}}}' for p, _ in STRESS_POPS) + ' \\\\')
    rules, c = [], 2
    for _ in STRESS_POPS:
        rules.append(f'\\cmidrule(lr){{{c}-{c + k - 1}}}')
        c += k
    out.append(''.join(rules))
    out.append('Method & ' + ' & '.join(h for _ in STRESS_POPS for _, h in STRESS_METRICS) + ' \\\\ \\midrule')
    for group, rows in STRESS_ROWS:
        out.append(f'\\multicolumn{{{k * len(STRESS_POPS) + 1}}}{{@{{}}l}}{{\\emph{{{group}}}}} \\\\')
        for meth, label in rows:
            vals = []
            for p, _ in STRESS_POPS:
                rec = strata[p]['methods'].get(meth)
                vals += [cell(rec[x]) if rec else '--' for x, _ in STRESS_METRICS]
            out.append(f'\\quad {label} & ' + ' & '.join(vals) + ' \\\\')
    out += ['\\bottomrule', '\\end{tabular}',
            '\\tablenote{}{Fresh seed generated after the guards\' protocol was fixed. Second header row: changed or deleted / preserved '
            'targets per suite. Miss over changed or deleted targets, Extra over '
            'preserved targets, Silent over all targets of the suite (changed plus preserved). Indentation: Python edits that keep every '
            'normalized line; changed means the enclosing syntax tree changed. Duplicate copy: an identical copy inserted near or far, above '
            'or below, or in another file, with the original kept, edited, deleted or moved. Short anchor: one-line anchors stratified by how '
            'often their text recurs. Compound: up to four operators on one anchor. AG: first copy guard; AGi: corrected copy guard; AG2: '
            'provenance rule (rejected). Constructed cells; rates are not prevalence estimates.}',
            '\\end{table*}', '']
    return '\n'.join(out)


def cell(r):
    return '--' if r is None or r.get('rate') is None else f"{100 * r['rate']:.1f}"


def locator_table(strata):
    cols = len(TABLE_POPS) * len(TABLE_METRICS)
    out = ['\\begin{table*}[t]', '\\caption{Locators With and Without the Safety Layer (\\%)}\\label{tab:locator}', '\\centering\\scriptsize',
           '\\setlength{\\tabcolsep}{1.5pt}', '\\begin{tabular}{@{}l' + ('r' * len(TABLE_METRICS) + '@{\\hspace{3pt}}') * (len(TABLE_POPS) - 1) + 'r' * len(TABLE_METRICS) + '@{}}\\toprule']
    out.append(' & ' + ' & '.join(f'\\multicolumn{{{len(TABLE_METRICS)}}}{{c}}{{{label}}}' for p, label in TABLE_POPS) + ' \\\\')
    out.append(' & ' + ' & '.join(f'\\multicolumn{{{len(TABLE_METRICS)}}}{{c}}{{$n{{=}}${num(strata[p]["n"])}}}' for p, _ in TABLE_POPS) + ' \\\\')
    rules, c = [], 2
    for _ in TABLE_POPS:
        rules.append(f'\\cmidrule(lr){{{c}-{c + len(TABLE_METRICS) - 1}}}')
        c += len(TABLE_METRICS)
    out.append(''.join(rules))
    out.append('Method & ' + ' & '.join(k for _ in TABLE_POPS for _, k in TABLE_METRICS) + ' \\\\ \\midrule')
    for group, rows in TABLE_ROWS:
        out.append(f'\\multicolumn{{{cols + 1}}}{{@{{}}l}}{{\\emph{{{group}}}}} \\\\')
        for meth, label in rows:
            vals = []
            for p, _ in TABLE_POPS:
                rec = strata[p]['methods'].get(meth)
                vals += [cell(rec[k]) if rec else '--' for k, _ in TABLE_METRICS]
            out.append(f'\\quad {label} & ' + ' & '.join(vals) + ' \\\\')
    out += ['\\bottomrule', '\\end{tabular}',
            '\\tablenote{}{Place: correct start among targets that survive. Miss: changed or deleted targets not returned for re-check. '
            'Silent: targets placed on wrong code without a request, over all targets. Misdir: targets placed on wrong code with a request, '
            'over all targets, including deleted code relocated onto other code. Lost: surviving targets with no location. Extra: requests on targets whose content is preserved. '
            '\\emph{Labels only} passes a locator\'s window through the quotation comparison that assigns the label; IG and AGi never move a window, '
            'so the other locators\' placement is unchanged, whereas the cascade\'s guarded rows also include VW, which changes window height and placement. '
            'Every locator sees the anchor\'s original path only (no Git rename hint). Real histories and student repositories are Python; the human-annotated regions span several languages '
            'and are seen as file pairs, so cross-file recovery is not exercised there. Held-out stress is a fresh seed of the indentation, '
            'duplicate, short-anchor and compound suites generated after the protocol was fixed. The pinned CodeMapper is not fully '
            'deterministic (Section~\\ref{sec:prefixes}); its guarded rows reuse the windows of its unguarded rows, so the two are paired. $^{*}$Composed after outcomes were read (exploratory).}',
            '\\end{table*}', '']
    return '\n'.join(out)


ID_ROWS = (('v0.85-off', 'Cascade'), ('v0.85-off-id', r'\quad + identity rule'), ('v0.55-alli', r'Guarded, $\theta{=}0.55$'),
           ('v0.55-alli-id', r'\quad + identity rule'), ('cm-seq', 'CodeMapper, labels'), ('cm-seq-id', r'\quad + identity rule'),
           ('cm-seq-gi', 'CodeMapper, guarded'), ('cm-seq-gi-id', r'\quad + identity rule'), ('cm-direct-gi', 'CodeMapper, direct'))
ID_METRICS = (('correct', 'Correct', 'pct'), ('wrong', 'Wrong', 'pct'), ('lost', 'Lost', 'pct'), ('missed_cumulative', 'Never|returned', 'k'),
              ('missed_last', 'Last|silent', 'k'), ('wrong_silent_last', 'Wrong,|silent', 'k'))


def identity_table(ch):
    if not ch:
        return ''
    p = ch['prefixes']['10']
    base = p['v0.85-off']
    changed = base['missed_cumulative']['n']
    head = ' & '.join(r'\shortstack[r]{' + h.replace('|', r'\\') + '}' for _, h, _ in ID_METRICS)
    out = [r'\begin{table}[t]', r'\caption{Ten Successive Commits: Identity Rule}\label{tab:identity}', r'\centering\footnotesize',
           r'\setlength{\tabcolsep}{2.4pt}', r'\begin{tabular}{@{}lrrrrrr@{}}\toprule', 'Method & ' + head + r' \\ \midrule']
    for meth, label in ID_ROWS:
        r = p[meth]
        out.append(label + ' & ' + ' & '.join(cell(r[k]) if kind == 'pct' else num(r[k]['k']) for k, _, kind in ID_METRICS) + r' \\')
    out += [r'\bottomrule', r'\end{tabular}',
            rf'\tablenote{{}}{{Endpoint after ten commits on {num(base["decidable"])} targets decidable at commit 10; correct, wrong and lost in \%. '
            f'Never returned and last silent count, of the {num(changed)} targets whose code had changed since the first commit, those never '
            "returned at any hop and those not returned by the last hop's request; wrong, silent counts endpoints on wrong code with no request "
            'at the last hop. Guarded: the cascade with IG+AGi+VW; CodeMapper with IG+AGi (placement as labels only, by construction). '
            'CodeMapper is replayed hop by hop; direct maps the first version to the last, guarded, and is shown for reference.}', r'\end{table}', '']
    return '\n'.join(out)


def main():
    path = latest()
    raw = path.read_bytes()
    data = json.loads(raw)['data']
    strata = data['strata']
    for pop, pname in POPS.items():
        if pop not in strata:
            continue
        s = strata[pop]
        m(f'wi{pname}N', num(s['n']))
        for meth, mname in METHODS.items():
            rec = s['methods'].get(meth)
            if rec is None:
                continue
            for key, kname in METRICS.items():
                r = rec[key]
                m(f'wi{pname}{mname}{kname}', pct(r))
                m(f'wi{pname}{mname}{kname}K', num(r['k']))
                m(f'wi{pname}{mname}{kname}N', num(r['n']))
            m(f'wi{pname}{mname}Err', num(rec['execution_errors']))
            # deleted targets reported present (relocated onto other code), over all deleted targets
            gk, gn = rec['counts']['gone_misreported'], rec['denominators']['gone']
            m(f'wi{pname}{mname}GoneKeptK', num(gk))
            m(f'wi{pname}{mname}GoneKeptN', num(gn))
            m(f'wi{pname}{mname}GoneKept', f'{100 * gk / gn:.1f}' if gn else '--')
    words = {'codemapper+IG+AG2 minus codemapper+quote': 'CmGtwoVsCmQ', 'codemapper+IG+AG2 minus codemapper+IG+AG': 'CmGtwoVsCmG',
             't0.85-IG+AG2+VW minus t0.85-IG+AG+VW': 'CasGtwoVsCasG', 'cmhybrid+IG+AG2 minus cmhybrid+quote': 'ChGtwoVsChQ',
             'cmhybrid+IG+AG2 minus deployed_native': 'ChGtwoVsDep', 'codemapper+IG+AG2 minus deployed_native': 'CmGtwoVsDep',
             'codemapper+IG+AGi minus codemapper+quote': 'CmGiVsCmQ', 'codemapper+IG+AGi minus codemapper+IG+AG': 'CmGiVsCmG',
             'codemapper+IG+AGi minus deployed_native': 'CmGiVsDep', 't0.85-IG+AGi+VW minus t0.85-IG+AG+VW': 'CasGiVsCasG',
             't0.55-IG+AGi+VW minus t0.55-IG+AG+VW': 'CalGiVsCalG', 't0.85-AGi minus t0.85-AG': 'CasAGiVsCasAG',
             'codemapper+AGi minus codemapper+AG': 'CmAGiVsCmAG', 'tracker+IG+AGi minus tracker+IG+AG': 'TrGiVsTrG',
             'cmhybrid+IG+AGi minus cmhybrid+quote': 'ChGiVsChQ', 'cmhybrid+IG+AGi minus deployed_native': 'ChGiVsDep',
             'cmhybrid+IG+AGi minus t0.85-IG+AGi+VW': 'ChGiVsCasGi', 'codemapper+IG+AG minus codemapper+quote': 'CmGVsCmQ'}
    for pop, pname in POPS.items():
        for contrast, cname in words.items():
            p = data['paired'].get(pop, {}).get(contrast)
            if p is None:
                continue
            for key, kname in METRICS.items():
                x = p['metrics'].get(key)
                if x is None or x['difference'] is None:
                    continue
                m(f'wi{pname}{cname}{kname}', f"{100 * x['difference']:.1f}")
                if x['cluster95']:
                    m(f'wi{pname}{cname}{kname}Lo', f"{100 * x['cluster95'][0]:.1f}")
                    m(f'wi{pname}{cname}{kname}Hi', f"{100 * x['cluster95'][1]:.1f}")
                e = x['exact_paired']
                m(f'wi{pname}{cname}{kname}B', num(e['b']))
                m(f'wi{pname}{cname}{kname}C', num(e['c']))
    # R03 major 3: prevalence at which the recommended guards (IG+AGi+VW) cost no more than the deployed cascade,
    # counting only missed re-checks (weight w) and unnecessary re-checks (weight 1). Guards also cut silent
    # misplacements on every population, so ignoring them makes each break-even point conservative.
    # The same break-even for CodeMapper (labels only -> +IG+AGi), the comparison a course replacing the locator faces.
    for pop, pname in (('real', 'Real'), ('students', 'Stu'), ('external:human-AB', 'Hum'), ('fresh', 'Fr')):
        meth = strata[pop]['methods']
        for base, guarded, tag in (('t0.85-deployed', 't0.85-IG+AGi+VW', ''), ('codemapper+quote', 'codemapper+IG+AGi', 'Cm')):
            dep, rec = meth[base], meth[guarded]
            saved = dep['missed']['rate'] - rec['missed']['rate']
            added = rec['false_recheck']['rate'] - dep['false_recheck']['rate']
            for w, wname in ((1, 'One'), (10, 'Ten')):
                m(f'wi{pname}{tag}BreakEven{wname}', '--' if saved <= 0 else f'{100 * max(added, 0) / (max(added, 0) + w * saved):.1f}')
        # AGi against AG: AGi saves false re-checks and may miss more; it is the cheaper guard only below this share p.
        for ag, agi, tag in (('t0.85-IG+AG+VW', 't0.85-IG+AGi+VW', 'Cas'), ('codemapper+IG+AG', 'codemapper+IG+AGi', 'Cm')):
            saved_f = meth[ag]['false_recheck']['rate'] - meth[agi]['false_recheck']['rate']
            added_m = meth[agi]['missed']['rate'] - meth[ag]['missed']['rate']
            for w, wname in ((1, 'One'), (10, 'Ten')):
                m(f'wi{pname}{tag}AGiBelow{wname}', '100' if added_m <= 0 else f'{100 * max(saved_f, 0) / (max(saved_f, 0) + w * added_m):.1f}')
    # WP I gives the contextual tracker the original path only (C6 strict_tracker), as CodeMapper and the cascade;
    # WP H2 gave it Git rename detection. Count the student placements that differ only by that rule.
    rows_path = EV / 'students/rows.json'
    if rows_path.exists():
        rows = json.loads(rows_path.read_bytes())
        rows = rows.get('data', rows) if isinstance(rows, dict) else rows
        renamed = sum(1 for r in rows if (r['methods'].get('tracker_adapter') or {}).get('placement')
                      and r['methods']['tracker_adapter']['placement'][0] != r['anchor_at'][0])
        m('wiStuTrRenamed', num(renamed))
    hyp = data['hypotheses']
    for rule in ('H1', 'H2'):
        sub = [h for h in hyp if h['hypothesis'] == rule]
        m(f'wiHyp{"One" if rule == "H1" else "Two"}Held', num(sum(h['descriptive'] for h in sub)))
        m(f'wiHyp{"One" if rule == "H1" else "Two"}Supported', num(sum(h['supported'] for h in sub)))
        m(f'wiHyp{"One" if rule == "H1" else "Two"}Total', num(len(sub)))
    for chain_key, P in (('chains', 'wiCh'), ('chains_agi', 'wiChI')):
        chain_macros(data.get(chain_key), P)
    if data.get('chains_agi'):
        m('wiChIGateChains', num(len(data['chains_agi']['gate']['chains'])))
        m('wiChIGateMismatches', num(data['chains_agi']['gate']['mismatches']))
    tables = {'table-locator.tex': locator_table(strata), 'table-identity.tex': identity_table(data.get('chains_agi')),
              'table-stress.tex': stress_table(strata)}
    names = [n for n, _ in macros]
    assert len(names) == len(set(names)), 'duplicate macro'
    write_outputs(path, raw, tables)


def chain_macros(ch, P):
    if ch:
        cw = {'v0.85-off': 'Off', 'v0.85-all': 'All', 'v0.85-all2': 'Alltwo', 'v0.55-all2': 'Caltwo', 'cm-seq': 'CmSeq',
              'cm-seq-g': 'CmSeqG', 'cm-direct': 'CmDirect', 'cm-direct-g': 'CmDirectG',
              'v0.85-alli': 'Alli', 'v0.55-alli': 'Cali', 'cm-seq-gi': 'CmSeqGi', 'cm-direct-gi': 'CmDirectGi'}
        hw = {'1': 'One', '2': 'Two', '3': 'Three', '5': 'Five', '10': 'Ten'}
        mw = {'correct': 'Acc', 'wrong': 'Wrong', 'lost': 'Lost', 'missed_cumulative': 'MissCum', 'missed_last': 'MissLast',
              'wrong_silent_cumulative': 'SilentCum', 'wrong_silent_last': 'SilentLast', 'last_exact_wrong': 'ExactWrong'}
        for h, hname in hw.items():
            for meth, r in ch['prefixes'][h].items():
                base = meth.replace('-id0.3', '').replace('-id0.7', '').replace('-id', '')
                if base not in cw:
                    continue
                suffix = 'IdLow' if meth.endswith('-id0.3') else 'IdHigh' if meth.endswith('-id0.7') else 'Id' if meth.endswith('-id') else ''
                for key, kname in mw.items():
                    m(f'{P}{cw[base]}{suffix}{kname}{hname}', pct(r[key]))
                    m(f'{P}{cw[base]}{suffix}{kname}{hname}K', num(r[key]['k']))
                m(f'{P}{cw[base]}{suffix}Decidable{hname}', num(r['decidable']))
        for contrast, p in ch['h10_contrasts'].items():
            a, b = contrast.split(' minus ')
            key = ''.join(cw[x.replace('-id', '')] + ('Id' if x.endswith('-id') else '') for x in (a, b))
            for k, kname in mw.items():
                x = p['metrics'][k]
                m(f'{P}D{key}{kname}', f"{100 * x['difference']:.1f}")
                m(f'{P}D{key}{kname}Lo', f"{100 * x['cluster95'][0]:.1f}")
                m(f'{P}D{key}{kname}Hi', f"{100 * x['cluster95'][1]:.1f}")


def write_outputs(path, raw, tables):
    OUT.mkdir(parents=True, exist_ok=True)
    text = '% Generated by tools/v11/build_wpi_tex.py from ' + path.name + '; do not edit.\n'
    text += ''.join(f'\\newcommand{{\\{n}}}{{{v}}}\n' for n, v in macros)
    (OUT / 'numbers-wpi.tex').write_text(text, encoding='utf-8')
    head = '% Generated by tools/v11/build_wpi_tex.py from ' + path.name + '; do not edit.\n'
    for name, body in tables.items():
        (OUT / name).write_text(head + body, encoding='utf-8')
    (OUT / 'numbers-wpi-provenance.json').write_text(json.dumps(dict(
        summary=str(path.relative_to(ROOT)).replace('\\', '/'), summary_sha256=hashlib.sha256(raw).hexdigest(),
        macros=len(macros), output_sha256=hashlib.sha256(text.encode()).hexdigest(),
        tables={n: hashlib.sha256((head + b).encode()).hexdigest() for n, b in tables.items()}), indent=1), encoding='utf-8')
    print(f'numbers-wpi.tex: {len(macros)} macros from {path.name}')


if __name__ == '__main__':
    main()
