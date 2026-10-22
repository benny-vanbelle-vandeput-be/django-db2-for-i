`bin/verify`: runs the offline tests and the corpus replay, writes changed SQL
to the goldens and corpus, then runs exactly what needs IBM i (unverified
goldens, new or changed own IBM i tests, one Django test per unverified corpus
entry, tests that left the skip lists) and writes the stamps of what passed to
the working tree, with a report. `bin/ibmi-test --affected` runs the same
selection without writing stamps. Git inside the container now trusts only the
checkout's mount (`/workspace`), which fixes "dubious ownership" in `bin/check`.
