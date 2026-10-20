"""Django-version axis: the only module allowed to check ``django.VERSION``.

Built from real differences between the supported Django versions (5.2 LTS,
6.0 and 6.1; docs/DJANGO_VERSIONS.md). Other modules import the named facts
below and never compare versions themselves (tests/offline/test_axes.py).

6.0 reaches end of life before 5.2, so the shims are grouped by when they can
go, not by version: each section's heading says when it is deleted. Dropping
a version also removes its goldens, its noxfile line and its pyproject range
(docs/DJANGO_VERSIONS.md, "Dropping a version").
"""

import django

# The running Django's feature release, e.g. "6.1". Golden files are kept per
# series (tests/offline/golden/<series>/...), since generated SQL can differ.
DJANGO_SERIES = f"{django.VERSION[0]}.{django.VERSION[1]}"

# --- Django 6.0 only (delete when 6.0 is dropped) ------------------------------------
# Nothing yet.

# --- Django 5.2 only (delete when 5.2 is dropped) ------------------------------------
# Nothing yet (5.2 support is phase 3, step B).

# --- Before 6.1: Django 6.0 and 5.2 (delete when both are dropped) -------------------
# Nothing yet.
