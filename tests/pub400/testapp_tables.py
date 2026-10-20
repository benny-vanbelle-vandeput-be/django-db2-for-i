"""The tests.testapp models whose tables the pub400 test modules create
(``testapp_tables`` in conftest.py)."""

from tests.testapp.models import (
    Account,
    Author,
    Book,
    Code,
    Contact,
    Defaults,
    Document,
    Link,
    Measure,
    Node,
    Profile,
    Schedule,
    Switch,
    Tag,
)

MODELS = (
    Author,
    Book,
    Node,
    Tag,
    Defaults,
    Document,
    Schedule,
    Code,
    Profile,
    Link,
    Account,
    Contact,
    Switch,
    Measure,
)
TABLES = {model._meta.db_table for model in MODELS}
