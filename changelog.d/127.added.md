A verification gate in CI (`nox -s gate`): every golden and corpus entry must
carry a verification stamp, except the goldens in
`tests/offline/golden/unverifiable.toml`, each with its reason and the
condition under which it becomes verifiable; TEST_STATUS shows their count.
The status generator ignores logs outside the current run set (modules not
supported yet, leftovers of older layouts).
