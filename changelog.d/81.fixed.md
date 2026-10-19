A nullable `BooleanField` used as a condition matched its NULL rows where it
should not: `filter(flag=False)`, `exclude(~F("flag"))`, a boolean annotation
in `filter(...=False)` / `exclude(...=True)`, and a `When(Q(flag=False))`.
Db2 for i treats NULL as false in `NOT flag`; boolean values used as
conditions are now compared with `TRUE` / `FALSE` (also index-friendly), and
the rows match Django on other databases.
