# Phase records

Each phase from section 9 of [CLAUDE.md](../../CLAUDE.md) gets one file,
`phase-<n>.md`, in this directory. It is written at the end of the phase, from
the merged pull requests, [CHANGELOG.md](../../CHANGELOG.md),
[DECISIONS.md](../DECISIONS.md), [IBMI_NOTES.md](../IBMI_NOTES.md) and
[TEST_STATUS.md](../TEST_STATUS.md), and links to them instead of repeating
them. A planned phase can get its file earlier as a proposal, marked
"Proposed, not yet approved", and is rewritten as a record when the phase is
done. Every file follows the template below.

```
# Phase <n>: <title from CLAUDE.md section 9>

> Status: Done (<YYYY-MM-DD of the last merged PR>) | In progress | Proposed, not yet approved

## Goal
<from CLAUDE.md section 9, including its "Done when" criteria if any>

## What was done
<bullets grouped by topic; each bullet ends with its PR link(s)>

## Key decisions
<bullets: the decision in one line + link to its docs/DECISIONS.md entry (GitHub heading anchor)>

## IBM i findings
<bullets: the finding in one line + link to its docs/IBMI_NOTES.md section>

## Test status at the end of the phase
<what was green at the end: offline tier, pub400 tier, Django modules, with numbers if recorded; link docs/TEST_STATUS.md>

## Carried forward
<open issues / tracks handed to later phases, with issue links>

## Links
<release tag(s) if any, CHANGELOG section, relevant docs>
```

## Phases

| Phase | Title | Record |
|---|---|---|
| 0 | Skeleton & environment | [phase-0.md](phase-0.md) |
| 1 | Minimal backend | [phase-1.md](phase-1.md) |
