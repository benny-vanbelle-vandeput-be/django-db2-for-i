CI: the commit status `ibmi-gate`. It is red while a pull request needs an
IBM i run and no posted run result (a comment with the `ibmi-run` marker by
the machine account or the maintainer) covers its current content, so a
missing label can't let a pull request through. It always runs main's
workflow and script, and treats the pull request only as data.
