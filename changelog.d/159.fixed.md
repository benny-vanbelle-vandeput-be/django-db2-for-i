CI classification: a pull request always gets its `run-ibmi` /
`needs-full-tier` labels, also when a quick second push cancelled the run
for the first one. The previous head now comes from the last completed
classification, which the PR comment names, not from the push event;
without such a comment the whole pull request is classified. The labels
are set before the comment is updated (#158 got no label).
