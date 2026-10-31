"""Inserts against the IBM i: returning columns through ``SELECT ... FROM
FINAL TABLE (INSERT ...)`` (phase 5, step A) on full model instances, and
``bulk_create()`` as multi-row inserts (step A2).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext

from django_db2_for_i.operations import BULK_MAX_LOB_PARAMS, BULK_MAX_PARAMS
from tests.testapp.models import (
    Author,
    Book,
    Defaults,
    Document,
    FiveTexts,
    Shelf,
    Tag,
    ThreeTexts,
)

pytestmark = pytest.mark.usefixtures("testapp_tables")


def test_create_reads_the_key_from_the_insert(live, empty) -> None:
    with CaptureQueriesContext(live) as queries:
        first = Author.objects.create(name="first")
        second = Author.objects.create(name="second")
    assert second.pk == first.pk + 1
    assert Author.objects.get(pk=second.pk).name == "second"
    statements = [query["sql"] for query in queries.captured_queries]
    assert all("FROM FINAL TABLE (INSERT INTO" in sql for sql in statements)
    assert not any("IDENTITY_VAL_LOCAL" in sql for sql in statements)


def test_save_sets_the_db_defaults_on_the_instance(live, empty) -> None:
    row = Defaults(number=5)
    row.save()
    # The values come from the insert itself, without a refresh.
    assert row.pk is not None
    assert row.number == 5
    assert row.text == "O'Brien 100%"
    assert row.flag is True
    assert row.amount == Decimal("1.50")
    assert row.day == dt.date(2026, 1, 2)
    assert row.nothing is None
    assert Defaults.objects.get(pk=row.pk).text == "O'Brien 100%"


def test_explicit_zero_key(live, empty) -> None:
    author = Author.objects.create(pk=0, name="zero")
    assert author.pk == 0
    assert Author.objects.get(pk=0).name == "zero"
    # The identity continues from its own counter (an explicit key does not move it).
    assert Author.objects.create(name="next").pk >= 1


def test_insert_in_a_transaction_is_rolled_back(live, empty) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        author = Author.objects.create(name="rolled back")
        Book.objects.create(author=author, title="gone", pages=1)
        raise RuntimeError("roll back")
    assert not Author.objects.exists()
    assert not Book.objects.exists()


def test_duplicate_key_raises_integrity_error(live, empty) -> None:
    Author.objects.create(pk=7, name="first")
    with pytest.raises(IntegrityError), transaction.atomic():
        Author.objects.create(pk=7, name="duplicate")
    assert Author.objects.get(pk=7).name == "first"


def _inserts(queries) -> list[str]:
    return [q["sql"] for q in queries.captured_queries if "INSERT INTO" in q["sql"]]


def test_bulk_create_sets_the_keys_in_input_order(live, empty) -> None:
    names = [f"author {i:03}" for i in range(300)]
    with CaptureQueriesContext(live) as queries:
        authors = Author.objects.bulk_create([Author(name=name) for name in names])
    assert len(_inserts(queries)) == 1
    assert all(author.pk is not None for author in authors)
    # Each instance got the key of its own row.
    stored = dict(Author.objects.values_list("pk", "name"))
    assert [stored[author.pk] for author in authors] == names
    assert len(set(stored)) == 300


def test_bulk_create_with_and_without_keys(live, empty) -> None:
    authors = Author.objects.bulk_create(
        [Author(pk=1000, name="given"), Author(name="generated"), Author(pk=1001, name="given too")]
    )
    assert [author.pk for author in authors][::2] == [1000, 1001]
    assert authors[1].pk is not None
    assert Author.objects.get(pk=authors[1].pk).name == "generated"
    assert Author.objects.count() == 3


def test_bulk_create_sets_the_db_defaults(live, empty) -> None:
    rows = Defaults.objects.bulk_create([Defaults(number=5), Defaults(text="set", flag=False)])
    assert [row.number for row in rows] == [5, -1]
    assert [row.text for row in rows] == ["O'Brien 100%", "set"]
    assert [row.flag for row in rows] == [True, False]
    assert rows[0].amount == Decimal("1.50")
    assert Defaults.objects.get(pk=rows[1].pk).text == "set"


def test_bulk_create_splits_at_the_parameter_limit(live, empty) -> None:
    author = Author.objects.create(name="many")
    columns = len([f for f in Book._meta.local_concrete_fields if not f.primary_key])
    per_statement = BULK_MAX_PARAMS // columns
    count = per_statement + 10
    with CaptureQueriesContext(live) as queries:
        books = Book.objects.bulk_create(
            [Book(author=author, title=f"book {i}", pages=i) for i in range(count)]
        )
    # A full batch at the limit is accepted, the rest goes in a second statement.
    assert len(_inserts(queries)) == 2
    assert Book.objects.count() == count
    assert [book.pages for book in books[-3:]] == [count - 3, count - 2, count - 1]
    assert Book.objects.get(pk=books[-1].pk).pages == count - 1


def test_bulk_create_splits_at_the_lob_limit(live, empty) -> None:
    # Two LOB columns, 1200 LOB markers in all: one statement would get PWS0001.
    count = 600
    with CaptureQueriesContext(live) as queries:
        documents = Document.objects.bulk_create(
            [Document(text=f"text {i}", data=None) for i in range(count)]
        )
    per_statement = BULK_MAX_LOB_PARAMS // 2
    assert len(_inserts(queries)) == 3
    assert per_statement * 2 < count <= per_statement * 3
    assert Document.objects.count() == count
    assert Document.objects.get(pk=documents[-1].pk).text == f"text {count - 1}"


@pytest.mark.parametrize(
    ("model", "lobs"), [(ThreeTexts, 3), (FiveTexts, 5)], ids=["three", "five"]
)
def test_bulk_create_divides_the_lob_limit_by_the_lob_columns(live, empty, model, lobs) -> None:
    # 600 rows in one statement or in batches of BULK_MAX_LOB_PARAMS rows would be
    # 1,800 or 3,000 LOB markers: PWS0001 above about 1,024 (probe qtemp_bulk_types).
    count = 600
    texts = [f.name for f in model._meta.fields if f.get_internal_type() == "TextField"]
    assert len(texts) == lobs
    code = {"code": lambda i: f"c{i}"} if model is FiveTexts else {}
    rows = [
        model(
            **{name: f"{name} {i}" for name in texts},
            **{name: make(i) for name, make in code.items()},
        )
        for i in range(count)
    ]
    with CaptureQueriesContext(live) as queries:
        created = model.objects.bulk_create(rows)
    per_statement = BULK_MAX_LOB_PARAMS // lobs
    assert per_statement * lobs <= 1024
    assert len(_inserts(queries)) == -(-count // per_statement)
    assert model.objects.count() == count
    assert model.objects.get(pk=created[-1].pk).first == f"first {count - 1}"


def test_bulk_create_ignore_conflicts_splits_at_the_lob_limit(live, empty) -> None:
    # A MERGE has the same limit: its markers are CAST(? AS NCLOB) in the source.
    FiveTexts.objects.create(code="c1", first="old", second="", third="", fourth="", fifth="")
    count = 300
    rows = [
        FiveTexts(code=f"c{i}", first="new", second="b", third="c", fourth="d", fifth="e")
        for i in range(count)
    ]
    with CaptureQueriesContext(live) as queries:
        FiveTexts.objects.bulk_create(rows, ignore_conflicts=True)
    merges = [q["sql"] for q in queries.captured_queries if q["sql"].startswith("MERGE INTO")]
    assert len(merges) == -(-count // (BULK_MAX_LOB_PARAMS // 5))
    assert FiveTexts.objects.count() == count
    assert FiveTexts.objects.get(code="c1").first == "old"
    assert FiveTexts.objects.get(code="c2").first == "new"


def test_bulk_create_in_a_transaction_is_rolled_back(live, empty) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        Author.objects.bulk_create([Author(name="a"), Author(name="b")])
        raise RuntimeError("roll back")
    assert not Author.objects.exists()


def test_bulk_create_with_a_duplicate_key_inserts_nothing(live, empty) -> None:
    Author.objects.create(pk=7, name="first")
    with pytest.raises(IntegrityError), transaction.atomic():
        Author.objects.bulk_create([Author(pk=8, name="new"), Author(pk=7, name="duplicate")])
    assert list(Author.objects.values_list("pk", flat=True)) == [7]


# --- ignore_conflicts / update_conflicts as MERGE (phase 5, step B) ------------------


def test_bulk_create_ignore_conflicts(live, empty) -> None:
    Author.objects.bulk_create([Author(pk=1, name="one"), Author(pk=2, name="two")])
    Author.objects.bulk_create(
        [Author(pk=2, name="TWO"), Author(pk=3, name="three")], ignore_conflicts=True
    )
    assert dict(Author.objects.values_list("pk", "name")) == {1: "one", 2: "two", 3: "three"}


def test_m2m_add_goes_through_merge_and_skips_existing_rows(live, empty) -> None:
    shelf = Shelf.objects.create()
    one, two = Author.objects.create(name="one"), Author.objects.create(name="two")
    with CaptureQueriesContext(live) as queries:
        shelf.authors.add(one)
        shelf.authors.add(one, two)
    on_the_table = [q["sql"] for q in queries.captured_queries if "SHELF_AUTHORS" in q["sql"]]
    assert len(on_the_table) == 2
    assert all(sql.startswith("MERGE INTO") for sql in on_the_table)
    assert sorted(shelf.authors.values_list("name", flat=True)) == ["one", "two"]


# What one job can show of a concurrent insert of the same key: the MERGE's own
# insert meets a duplicate key. Two jobs need a dedicated IBM i (docs/IBMI_NOTES.md,
# "MERGE under concurrency").
@pytest.mark.parametrize("in_transaction", [False, True], ids=["autocommit", "atomic"])
def test_a_duplicate_key_in_a_merge_raises_and_undoes_the_statement(
    live, empty, in_transaction
) -> None:
    Author.objects.create(pk=1, name="existing")
    rows = [Author(pk=2, name="new"), Author(pk=3, name="other"), Author(pk=2, name="again")]
    with pytest.raises(IntegrityError) as caught:
        if in_transaction:
            with transaction.atomic():
                Author.objects.bulk_create(rows, ignore_conflicts=True)
        else:
            Author.objects.bulk_create(rows, ignore_conflicts=True)
    assert "SQL0803" in str(caught.value)
    # Also the rows without a conflict: the whole statement is undone.
    assert list(Author.objects.values_list("pk", flat=True)) == [1]


def test_bulk_create_update_conflicts(live, empty) -> None:
    author = Author.objects.create(name="a")
    Book.objects.bulk_create(
        [Book(pk=1, author=author, title="old", pages=1), Book(pk=2, author=author, title="x")]
    )
    books = Book.objects.bulk_create(
        [
            Book(pk=1, author=author, title="new", pages=99),
            Book(pk=3, author=author, title="added", pages=3),
        ],
        update_conflicts=True,
        unique_fields=["id"],
        update_fields=["title", "pages"],
    )
    assert len(books) == 2
    rows = dict(Book.objects.values_list("pk", "title"))
    assert rows == {1: "new", 2: "x", 3: "added"}
    assert Book.objects.get(pk=1).pages == 99


def test_bulk_create_ignore_conflicts_on_another_unique_key(live, empty) -> None:
    """ignore_conflicts matches every unique key, not only the primary key:
    a new UUID key with an existing unique label is skipped."""
    Tag.objects.create(label="same")
    Tag.objects.bulk_create([Tag(label="same"), Tag(label="other")], ignore_conflicts=True)
    assert sorted(Tag.objects.values_list("label", flat=True)) == ["other", "same"]
