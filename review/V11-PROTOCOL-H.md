# V11 WPH1: Selection protocol and discovery

## H1 criteria (verbatim from the brief)

- Public, not a fork, not archived-as-template; primary language Python; ≥2,000 Python LOC at the head of the default branch; ≥60 first-parent commits; ≥2 distinct commit authors (team work).
- Created between 2016-01-01 and 2022-11-29 with ≥90% of first-parent commits before 2022-11-30 (pre-dates widespread LLM coding assistants; record the share). A secondary 2023+ stratum may be collected under the same rules and reported separately.
- Explicit evidence of student authorship in the README or repository description: a course code, "capstone", "final year project", "senior design", "course project", "semester project", or a university/course name. Store the matched sentence (≤200 chars) as the evidence string.
- Exclusions: tutorials/course materials authored by instructors, forks/mirrors of templates, repositories with vendored third-party code making up >50% of the Python LOC, notebooks-only repositories.
- Discovery: GitHub search API queries listed verbatim in the protocol; candidates deduplicated and sorted by repository id; criteria applied by script; keep the first 20 passing repositories (and record how many were screened and rejected per criterion).

## Search queries (verbatim)

The script submits these query strings, unchanged, to GitHub's Search Repositories API, in this order:

1. `capstone language:python created:2016-01-01..2022-11-29`
2. `"final year project" language:python created:2016-01-01..2022-11-29`
3. `"senior design" language:python created:2016-01-01..2022-11-29`
4. `"course project" language:python created:2016-01-01..2022-11-29`
5. `"semester project" language:python created:2016-01-01..2022-11-29`
6. `"capstone project" language:python created:2016-01-01..2022-11-29`
7. `"final year" "course project" language:python created:2016-01-01..2022-11-29`
8. `"senior project" university language:python created:2016-01-01..2022-11-29`

Each query is paged in API page order up to GitHub's 1,000-result search limit. Search results are unioned by numeric repository id; duplicate ids count once. The API's reported `total_count`, pages fetched, and truncation at the 1,000-result ceiling are recorded in the discovery output.

## Screening order

For the deduplicated candidate set, sort ascending by numeric GitHub repository id. Screen in that order and stop after 20 passing repositories. For every candidate actually screened, evaluate and record each criterion in this order:

1. Repository is public, not a fork, and not archived.
2. Primary repository language is Python.
3. Created date is within 2016-01-01 through 2022-11-29 inclusive.
4. Explicit student-authorship evidence exists in the repository description or README and yields a matched sentence no longer than 200 characters.
5. Repository is not instructor-authored tutorial/course material and not a fork/mirror of a template. Automated rejection uses explicit README/description markers (`instructor`, `lecturer`, `course materials`, `teaching materials`, `tutorial`, `template`, `boilerplate`, `starter code`, `starter repository`, `mirror`, `fork of`) only when they occur in authorship/context patterns defined in the screening script; generic mentions are not sufficient.
6. Repository is not notebooks-only. It must contain at least one tracked `.py` file at the selected head.
7. At least 2,000 nonblank, non-comment Python source lines exist at the selected head. Generated/vendor paths are tracked separately for the vendor share.
8. At least 60 first-parent commits exist at the selected head.
9. At least two distinct commit authors exist across first-parent commits. Author identifiers are used transiently for counting and are never written to output.
10. At least 90% of first-parent commits have author dates before 2022-11-30. Record the exact numerator, denominator and share; a missing/invalid date fails this criterion.
11. Vendored third-party code is no more than 50% of Python LOC. The script classifies vendored paths by fixed path-component and filename markers; record total Python LOC, vendored Python LOC and share.

Continue evaluating all criteria for each screened candidate even if an earlier criterion fails, unless an API/clone failure makes a metric unavailable. Mark unavailable separately; it never counts as a pass. Rejection counts are non-exclusive because a repository may fail multiple criteria. Do not screen candidates after the twentieth passing repository. Accordingly, screened counts and per-criterion rejection counts describe only the deterministic prefix needed to identify the first 20 passers.

## Selection and privacy

The selection is the first 20 repositories in ascending numeric repository-id order that pass every criterion. If fewer than 20 pass among candidates available through the frozen queries, select and report the true number; do not relax criteria. Pin full head commit SHAs on the default branch. The private selected file may contain repository full names as public repository identifiers, branch names, commit hashes, matched evidence sentences, and aggregate repository metrics. Never persist contributor logins or emails. Public results use only S1..Sn labels and aggregate/descriptive metrics; they contain no repository names or personal logins.

GitHub access is read-only. Clones used for commit and source metrics stay under `evidence/v11-wph/private/tmp/`. No relocation runs, oracle, or additional clones for H2 are in scope.
