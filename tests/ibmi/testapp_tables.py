"""The tests.testapp models whose tables the IBM i test modules create
(``testapp_tables`` in conftest.py)."""

from tests.testapp.models import (
    Account,
    Article,
    Author,
    Book,
    Code,
    Contact,
    Defaults,
    Document,
    FiveTexts,
    Link,
    Measure,
    Node,
    Profile,
    Rating,
    Schedule,
    Shelf,
    Switch,
    Tag,
    ThreeTexts,
)

MODELS = (
    Author,
    Book,
    Node,
    Tag,
    Defaults,
    Document,
    ThreeTexts,
    FiveTexts,
    Shelf,
    Schedule,
    Code,
    Profile,
    Link,
    Account,
    Contact,
    Switch,
    Measure,
    Rating,
    Article,
)
TABLES = {model._meta.db_table for model in MODELS} | {Shelf.authors.through._meta.db_table}
