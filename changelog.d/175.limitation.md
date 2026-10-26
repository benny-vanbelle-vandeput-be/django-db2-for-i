Known limitations: SQL0910 in a migration only hits a column that really
holds NULLs (verified), or rows changed by `RunPython`/`RunSQL` before a
schema change of the same table. The workaround is stated plainly:
`atomic = False`, or a separate data migration before the schema change.
