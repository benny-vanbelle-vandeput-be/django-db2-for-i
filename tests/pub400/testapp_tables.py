"""The tests.testapp models whose tables the pub400 test modules create
(``testapp_tables`` in conftest.py)."""

from tests.testapp.models import (
    Author,
    Book,
    Code,
    Defaults,
    Document,
    Link,
    Node,
    Profile,
    Schedule,
    Tag,
)

MODELS = (Author, Book, Node, Tag, Defaults, Document, Schedule, Code, Profile, Link)
TABLES = {model._meta.db_table for model in MODELS}
