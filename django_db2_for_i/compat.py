"""Django-version axis: the only module allowed to check ``django.VERSION``.

Built from real differences between supported Django versions in phase 3.
Adding or dropping a Django version must be a local change here.
"""

import django

# The running Django's feature release, e.g. "6.1". Golden files are kept per
# series (tests/offline/golden/<series>/...), since generated SQL can differ.
DJANGO_SERIES = f"{django.VERSION[0]}.{django.VERSION[1]}"
