A condition selected as a value (`annotate(b=Q(...))`, also in `values()`,
GROUP BY and `update()`) returned `False` where its result is unknown because
of a NULL; it now returns `None`, as on other backends
([#75](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/75)).
