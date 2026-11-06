"""K6 normalized textual oracle; no location is inferred for rewrites."""

def lines(text):
    return [(line.strip(), i) for i, line in enumerate(text.splitlines(), 1) if line.strip()]


def occurrences(haystack, needle):
    if not needle:
        return []
    values = [s for s, _ in haystack]
    return [(i, i + len(needle)) for i in range(len(values) - len(needle) + 1)
            if values[i:i + len(needle)] == needle]


def classify(original, suggestion, current):
    if current is None:
        return 'gone-file', None
    o = [s for s, _ in lines(original)]
    s = [s for s, _ in lines(suggestion)]
    if not o or o == s:
        raise ValueError('ineligible original or unchanged suggestion')
    file_lines = lines(current)
    os = occurrences(file_lines, o)
    ss = occurrences(file_lines, s)
    def span(run):
        return file_lines[run[0]][1], file_lines[run[1]-1][1]
    if not s:
        return ('applied-deletion', None) if not os else (('untouched', span(os[0])) if len(os) == 1 else ('ambiguous', None))
    if occurrences([(x, i) for i, x in enumerate(s)], o):
        os = [r for r in os if not any(a <= r[0] and r[1] <= b for a, b in ss)]
    if len(ss) == 1 and not os:
        return 'applied', span(ss[0])
    if len(os) == 1 and not ss:
        return 'untouched', span(os[0])
    if os or ss:
        return 'ambiguous', None
    return 'rewritten', None
