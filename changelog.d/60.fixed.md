A parameterized statement on an IBM i service (a QSYS2 table function or view
that calls system APIs) failing with SQL0443 left the connection unusable:
every later statement failed with SQL0519. The driver now marks such a
connection unusable (the original error is raised; a later SQL0519 explains
that a new connection is needed), so Django replaces it. The test library
journal check no longer passes a parameter to `QSYS2.JOURNAL_INFO`.
