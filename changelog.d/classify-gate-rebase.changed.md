CI: a conflict-free rebase over `main` commits that change only the IBM i gate
(`.github/workflows/ibmi-gate.yml`, `scripts/ibmi_gate.py`) no longer needs a
new IBM i run. In their own pull request those files still count as "needs
full tier" for the maintainer's review. The gate workflow's job is now called
`ibmi-gate-check`. The status it sets, `ibmi-gate`, is unchanged.
