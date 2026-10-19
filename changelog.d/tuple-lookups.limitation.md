A condition selected as a value (`annotate(b=Q(...))`) returns `False` where
SQL gives unknown because of a NULL, not `None` as on other backends
([#75](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/75)).
