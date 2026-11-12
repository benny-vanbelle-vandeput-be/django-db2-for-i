"""select_for_update() with a second job (phase 7, step 5; probe lib_select_for_update, #237).

Two connections at once, within PUB400's rule for lock tests (#236): the test's own and
`second_job`. The testapp tables get a record wait of 2 seconds (CHGPF WAITRCD(2), on
their system names), so a blocked statement of the second job fails with SQL0913 after
about 2 seconds instead of the default wait.
"""

import pytest
from django.db import DatabaseError, transaction

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.usefixtures("testapp_tables")

WAIT_SECONDS = 2


@pytest.fixture
def second_job(live):
    """A second connection with the same settings: another job on the server."""
    from django.db import connections

    wrapper = connections[live.alias]
    other = type(wrapper)(dict(wrapper.settings_dict), alias="second_job")
    try:
        yield other
    finally:
        other.close()


@pytest.fixture
def rows(live, empty):
    """Two authors with a book each; the tables wait 2 seconds for a locked row."""
    with live.cursor() as cursor:
        for table in (Author._meta.db_table, Book._meta.db_table):
            cursor.execute(
                "SELECT SYSTEM_TABLE_SCHEMA, SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
                "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s",
                [table.upper()],
            )
            # The catalog pads system names with blanks; CL takes them bare (CPD0104).
            library, system_name = (name.strip() for name in cursor.fetchone())
            cursor.execute(
                f"CALL QSYS2.QCMDEXC('CHGPF FILE({library}/{system_name}) WAITRCD({WAIT_SECONDS})')"
            )
    first = Author.objects.create(name="first")
    second = Author.objects.create(name="second")
    books = [Book.objects.create(author=a, title=f"{a.name}'s book") for a in (first, second)]
    return first, second, books


def _blocked(second_job, sql: str, params=()) -> bool:
    """Whether the second job's statement is refused because a row is locked."""
    try:
        with second_job.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.description:
                cursor.fetchall()
    except DatabaseError as exc:
        assert "SQL0913" in str(exc), exc
        return True
    return False


def _update_author(pk) -> tuple[str, list]:
    return f'UPDATE "{Author._meta.db_table.upper()}" SET "NAME" = %s WHERE "ID" = %s', ["x", pk]


def _update_book(pk) -> tuple[str, list]:
    return f'UPDATE "{Book._meta.db_table.upper()}" SET "TITLE" = %s WHERE "ID" = %s', ["x", pk]


def test_the_locked_row_waits_until_the_transaction_ends(live, rows, second_job) -> None:
    first, second, _ = rows
    with transaction.atomic():
        locked = list(Author.objects.select_for_update().filter(pk=first.pk))
        assert [a.pk for a in locked] == [first.pk]
        assert _blocked(second_job, *_update_author(first.pk))
        assert not _blocked(second_job, *_update_author(second.pk))
    assert not _blocked(second_job, *_update_author(first.pk))


def test_the_lock_ends_with_a_rollback(live, rows, second_job) -> None:
    first, _, _ = rows
    with pytest.raises(RuntimeError), transaction.atomic():
        list(Author.objects.select_for_update().filter(pk=first.pk))
        raise RuntimeError("roll back")
    assert not _blocked(second_job, *_update_author(first.pk))


def test_skip_locked_skips_the_locked_rows(live, rows, second_job) -> None:
    first, second, _ = rows
    queryset = Author.objects.select_for_update(skip_locked=True).order_by("pk")
    with transaction.atomic():
        sql, params = queryset.query.get_compiler(using=live.alias).as_sql()
        assert sql.endswith("FOR UPDATE WITH RS SKIP LOCKED DATA")
        list(Author.objects.select_for_update().filter(pk=first.pk))
        second_job.set_autocommit(False)
        try:
            with second_job.cursor() as cursor:
                cursor.execute(sql, params)
                assert [row[0] for row in cursor.fetchall()] == [second.pk]
        finally:
            second_job.rollback()
            second_job.set_autocommit(True)


def test_a_slice_locks_only_its_rows(live, rows, second_job) -> None:
    first, second, _ = rows
    with transaction.atomic():
        locked = list(Author.objects.select_for_update().order_by("pk")[:1])
        assert [a.pk for a in locked] == [first.pk]
        assert _blocked(second_job, *_update_author(first.pk))
        assert not _blocked(second_job, *_update_author(second.pk))


def test_of_self_locks_the_selected_rows(live, rows, second_job) -> None:
    first, _, _ = rows
    queryset = Author.objects.select_for_update(of=("self",)).filter(pk=first.pk)
    with transaction.atomic():
        sql, _ = queryset.query.get_compiler(using=live.alias).as_sql()
        assert sql.endswith('FOR UPDATE OF "ID" WITH RS')
        list(queryset)
        assert _blocked(second_job, *_update_author(first.pk))


def test_a_join_locks_the_rows_of_every_table(live, rows, second_job) -> None:
    """select_related() joins, which cannot take FOR UPDATE (SQL0511): the backend
    writes WITH RS USE AND KEEP EXCLUSIVE LOCKS, which locks the book and its author."""
    first, second, books = rows
    queryset = Book.objects.select_related("author").select_for_update().filter(pk=books[0].pk)
    with transaction.atomic():
        sql, _ = queryset.query.get_compiler(using=live.alias).as_sql()
        assert sql.endswith("WITH RS USE AND KEEP EXCLUSIVE LOCKS")
        (book,) = queryset
        assert book.author.pk == first.pk
        assert _blocked(second_job, *_update_book(books[0].pk))
        assert _blocked(second_job, *_update_author(first.pk))
        assert not _blocked(second_job, *_update_book(books[1].pk))
        assert not _blocked(second_job, *_update_author(second.pk))
    assert not _blocked(second_job, *_update_author(first.pk))


def test_a_locked_row_can_be_updated_in_the_same_transaction(live, rows) -> None:
    first, _, _ = rows
    with transaction.atomic():
        author = Author.objects.select_for_update().get(pk=first.pk)
        author.name = "changed"
        author.save()
    assert Author.objects.get(pk=first.pk).name == "changed"
