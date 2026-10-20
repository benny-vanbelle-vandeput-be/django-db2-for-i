"""Lookups against the IBM i (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import pytest

from tests.testapp.models import Author

pytestmark = pytest.mark.usefixtures("testapp_tables")


def names(queryset) -> list[str]:
    return sorted(queryset.values_list("name", flat=True))


def test_iexact_with_wildcard_characters(live, empty) -> None:
    """iexact compares the value as it is: _, % and \\ are no wildcards there,
    and must not match other rows."""
    for name in ("a_b", "axb", "x%y", "xzzy", "back\\slash", "backxslash"):
        Author.objects.create(name=name)
    assert names(Author.objects.filter(name__iexact="A_B")) == ["a_b"]
    assert names(Author.objects.filter(name__iexact="X%Y")) == ["x%y"]
    assert names(Author.objects.filter(name__iexact="BACK\\SLASH")) == ["back\\slash"]
    # The LIKE lookups keep escaping the wildcards.
    assert names(Author.objects.filter(name__icontains="_")) == ["a_b"]
    assert names(Author.objects.filter(name__istartswith="X%")) == ["x%y"]


def test_iexact_with_non_ascii_letters(live, empty) -> None:
    """UPPER() on NVARCHAR: how Db2 for i uppercases é, Ü and ß."""
    for name in ("café", "MÜNCHEN", "straße"):
        Author.objects.create(name=name)
    assert names(Author.objects.filter(name__iexact="CAFÉ")) == ["café"]
    assert names(Author.objects.filter(name__iexact="münchen")) == ["MÜNCHEN"]
    assert names(Author.objects.filter(name__iexact="STRASSE")) == []
    assert names(Author.objects.filter(name__iexact="STRAßE")) == ["straße"]


def test_values_longer_than_the_column_never_match_a_truncated_row(live, empty) -> None:
    """A value longer than NVARCHAR(100) must not fail (CWB0111) and must never
    match a row holding its truncated form."""
    truncated = "n" * 100
    longer = truncated + "x"  # 101 characters
    Author.objects.create(name=truncated)
    Author.objects.create(name="other")
    assert names(Author.objects.filter(name=longer)) == []
    assert names(Author.objects.filter(name__in=[longer, "other"])) == ["other"]
    assert names(Author.objects.exclude(name__in=[longer])) == sorted([truncated, "other"])
    assert names(Author.objects.exclude(name=longer)) == sorted([truncated, "other"])
    assert names(Author.objects.filter(name__gt=longer)) == ["other"]  # "nnn...n" < "nnn...nx"
    assert names(Author.objects.filter(name__lt=longer)) == [truncated]


def test_utf16_units_decide_whether_a_value_fits(live, empty) -> None:
    from tests.testapp.models import Tag

    fits = "e" * 49 + "é"
    too_long = "e" * 49 + "\U0001f600"  # 50 by len(), 51 UTF-16 units
    Tag.objects.create(label=fits)
    assert list(Tag.objects.filter(label=fits).values_list("label", flat=True)) == [fits]
    assert Tag.objects.filter(label=too_long).count() == 0


def test_expressions_compare_long_values(live, empty) -> None:
    from django.db.models.functions import Lower, Substr

    Author.objects.create(name="Abcdef")
    lowered = Author.objects.annotate(low=Lower("name"))
    assert names(lowered.filter(low="abcdef")) == ["Abcdef"]
    assert names(lowered.filter(low="x" * 150)) == []
    start = Author.objects.annotate(start=Substr("name", 1, 3))
    assert names(start.filter(start="Abc")) == ["Abcdef"]
    assert names(start.filter(start="Abcdef")) == []  # longer than SUBSTR(..., 1, 3)


def test_in_subquery_outside_a_search_condition(live, empty) -> None:
    """IN (subquery) as a selected value and in XOR (CASE WHEN on Db2 for i, where
    IN (subquery) is rejected) gives exactly the rows of the same condition in a
    WHERE clause (plain IN): with a NULL in x and NULLs in the subquery, positive
    and negated; the positive form also equals raw SQL IN."""
    from django.db.models import Q

    from tests.testapp.models import Link

    a1, a2, a3 = (Author.objects.create(name=n) for n in ("a1", "a2", "a3"))
    links = [Link.objects.create(author=a) for a in (a1, a2, a3, None)]  # x NULL in the last
    by_name = {
        "match and NULL": Link.objects.filter(pk__in=[links[0].pk, links[3].pk]),
        "no NULL": Link.objects.filter(pk=links[1].pk),
        "only NULL": Link.objects.filter(pk=links[3].pk),
        "empty": Link.objects.filter(pk=-1),
    }
    table, column = '"TESTAPP_LINK"', '"AUTHOR_ID"'
    for name, rows in by_name.items():
        ids = ", ".join(str(pk) for pk in rows.values_list("pk", flat=True)) or "-1"
        with live.cursor() as cursor:
            plain = {}
            for op in ("IN", "NOT IN"):
                cursor.execute(
                    f"SELECT ID FROM {table} WHERE {column} {op} "
                    f"(SELECT {column} FROM {table} WHERE ID IN ({ids}))"
                )
                plain[op] = {row[0] for row in cursor.fetchall()}
        subquery = rows.values("author")
        selected = Link.objects.annotate(
            yes=Q(author__in=subquery), no=~Q(author__in=subquery)
        ).values_list("pk", "yes", "no")
        assert {pk for pk, yes, _ in selected if yes} == plain["IN"], name
        # ~Q on a nullable column is Django's NOT (x IN (...) AND x IS NOT NULL), not
        # SQL's NOT IN: compare with the same ~Q in WHERE (plain IN there).
        negated = set(Link.objects.filter(~Q(author__in=subquery)).values_list("pk", flat=True))
        assert {pk for pk, _, no in selected if no} == negated, name
        assert negated >= plain["NOT IN"], name
        xor = Link.objects.filter(Q(author__in=subquery) ^ Q(pk=links[1].pk))
        expected = plain["IN"] ^ {links[1].pk}
        assert set(xor.values_list("pk", flat=True)) == expected, name


def test_tuple_in_subquery(live, empty) -> None:
    """A two-column relation filtered by a subquery: (a, b) IN (...) in WHERE
    (positive and negated), as a selected value (positive and negated) and in XOR
    gives the rows of raw SQL row-value IN / NOT IN, with a NULL in one column of x."""
    from django.db.models import Q

    from tests.testapp.models import Account, Contact

    for company, number in (("a", 1), ("b", 2), ("c", 3)):
        Account.objects.create(company=company, number=number)
    contacts = [
        Contact.objects.create(company=company, account_number=number)
        for company, number in (("a", 1), ("a", None), ("b", 2), ("c", 9))
    ]
    by_name = {
        "one match": Account.objects.filter(number=1),
        "two matches": Account.objects.filter(number__lte=2),
        "no match": Account.objects.filter(number=3),
        "empty": Account.objects.filter(number=-1),
    }
    for name, accounts in by_name.items():
        numbers = ", ".join(str(n) for n in accounts.values_list("number", flat=True)) or "-1"
        with live.cursor() as cursor:
            plain = {}
            for op in ("IN", "NOT IN"):
                cursor.execute(
                    f'SELECT ID FROM "TESTAPP_CONTACT" WHERE (COMPANY, ACCOUNT_NUMBER) {op} '
                    f'(SELECT COMPANY, NUMBER FROM "TESTAPP_ACCOUNT" WHERE NUMBER IN ({numbers}))'
                )
                plain[op] = {row[0] for row in cursor.fetchall()}
        where = set(Contact.objects.filter(account__in=accounts).values_list("pk", flat=True))
        assert where == plain["IN"], name
        selected = Contact.objects.annotate(
            yes=Q(account__in=accounts), no=~Q(account__in=accounts)
        ).values_list("pk", "yes", "no")
        assert {pk for pk, yes, _ in selected if yes} == plain["IN"], name
        # Three-valued like SQL's row-value NOT IN: ("a", NULL) NOT IN (("a", 1)) is
        # UNKNOWN, as a selected value and in WHERE.
        assert {pk for pk, _, no in selected if no} == plain["NOT IN"], name
        negated = set(Contact.objects.filter(~Q(account__in=accounts)).values_list("pk", flat=True))
        assert negated == plain["NOT IN"], name
        xor = Contact.objects.filter(Q(account__in=accounts) ^ Q(pk=contacts[2].pk))
        assert set(xor.values_list("pk", flat=True)) == plain["IN"] ^ {contacts[2].pk}, name


def test_tuple_in_subquery_in_a_case_context_uses_the_rewrite(live, empty) -> None:
    """A ForeignObject __in=<subquery> in XOR, as a selected value and as a When
    condition: Db2 for i rejects IN (subquery) inside CASE WHEN (SQL0115), so the
    search-condition context of WHERE must not leak into these CASE contexts.
    Every statement uses the rewrite and holds no plain IN (subquery)."""
    from django.db import connection
    from django.db.models import Case, Q, Value, When
    from django.test.utils import CaptureQueriesContext

    from tests.testapp.models import Account, Contact

    for company, number in (("a", 1), ("b", 2)):
        Account.objects.create(company=company, number=number)
    for company, number in (("a", 1), ("a", None), ("b", 2), ("c", 9)):
        Contact.objects.create(company=company, account_number=number)
    accounts = Account.objects.filter(number=1)
    in_accounts = Q(account__in=accounts)
    querysets = {
        "xor": Contact.objects.filter(in_accounts ^ Q(company="c")).values_list(
            "company", "account_number"
        ),
        "selected": Contact.objects.annotate(b=in_accounts).values_list(
            "company", "account_number", "b"
        ),
        "when": Contact.objects.annotate(
            x=Case(When(in_accounts, then=Value(1)), default=Value(0))
        ).values_list("company", "account_number", "x"),
    }
    expected = {
        "xor": {("a", 1), ("c", 9)},
        # ("a", NULL) IN (("a", 1)) is UNKNOWN: no When match, None as a value (#75).
        "selected": {("a", 1, True), ("a", None, None), ("b", 2, False), ("c", 9, False)},
        "when": {("a", 1, 1), ("a", None, 0), ("b", 2, 0), ("c", 9, 0)},
    }
    for name, queryset in querysets.items():
        with CaptureQueriesContext(connection) as captured:
            rows = set(queryset)
        sql = captured.captured_queries[-1]["sql"]
        assert rows == expected[name], name
        assert "DJDB2I_IN" in sql, name
        # XOR's first half is a search condition (row-value IN there is fine).
        assert " IN (SELECT" not in sql[sql.index("CASE WHEN") :], name


def test_tuple_lookups_match_the_reference(live, empty) -> None:
    """Every lookup on a multi-column relation, in every context, gives the rows of
    the reference (SQLite with supports_tuple_lookups, tests/tuple_lookup_scenarios.py),
    except the listed known differences."""
    from tests import tuple_lookup_scenarios as scenarios

    scenarios.create("default")
    actual = {name: scenarios.rows(qs) for name, qs in scenarios.querysets("default").items()}
    expected = dict(scenarios.EXPECTED)
    for differences in scenarios.KNOWN_DIFFERENCES.values():
        expected.update(differences)
    assert actual == expected


def test_values_longer_than_their_column(live, empty) -> None:
    """A tuple lookup value longer than its column matches nothing (it is never cut
    short to match a row holding the shortened value), and a selected Value longer
    than its field comes back whole."""
    from django.db.models import Value

    from tests.testapp.models import Account, Contact

    account = Account.objects.create(company="a", number=1)
    Contact.objects.create(company="a", account_number=1)
    longer = Account(id=account.pk, company="a\U0001f600", number=1)  # 3 UTF-16 units
    assert list(Contact.objects.filter(account=longer)) == []
    assert Contact.objects.filter(account=account).count() == 1
    field = Account._meta.get_field("company")
    selected = Contact.objects.annotate(v=Value("abc\U0001f600", output_field=field))
    assert list(selected.values_list("v", flat=True)) == ["abc\U0001f600"]


def test_numeric_values_that_do_not_fit_the_column(live, empty) -> None:
    """Issue #69: integers out of the column's range in IN lists and ranges, and
    Decimals with more digits than DECIMAL(5, 2), match exactly the rows of exact
    arithmetic. The rows hold the truncated (1.00) and the rounded (1.01) value of
    1.005, which must never match; values are never rounded or truncated."""
    from decimal import Decimal

    from django.db import NotSupportedError

    from tests.testapp.models import Measure

    rows = {
        "truncated": (1, Decimal("1.00"), 1),
        "rounded": (32767, Decimal("1.01"), 2**62),
        "high": (-32768, Decimal("999.99"), None),
        "negative": (0, Decimal("-1.00"), -1),
        "null": (None, None, None),
        "zero": (2, Decimal("0.00"), 0),
    }
    pk = {}
    for name, (small, amount, big) in rows.items():
        pk[Measure.objects.create(small=small, amount=amount, big=big).pk] = name

    def names(queryset) -> list[str]:
        return sorted(pk[key] for key in queryset.values_list("pk", flat=True))

    measures = Measure.objects
    d = Decimal
    # Integers out of the SMALLINT range.
    assert names(measures.filter(small__in=[1, 100000])) == ["truncated"]
    assert names(measures.filter(small__in=[100000, -100000])) == []
    assert names(measures.exclude(small__in=[1, 100000])) == [
        "high", "negative", "null", "rounded", "zero",
    ]  # fmt: skip
    assert names(measures.filter(small__range=(0, 100000))) == [
        "negative", "rounded", "truncated", "zero",
    ]  # fmt: skip
    assert names(measures.filter(small__range=(-100000, 0))) == ["high", "negative"]
    # An integer beyond BIGINT (sent as a Decimal).
    assert names(measures.filter(big__in=[2**62, 10**20])) == ["rounded"]
    # Decimals with more digits than DECIMAL(5, 2): never rounded or truncated.
    assert names(measures.filter(amount=d("1.005"))) == []
    assert names(measures.filter(amount__gt=d("1.005"))) == ["high", "rounded"]
    assert names(measures.filter(amount__lt=d("1.005"))) == ["negative", "truncated", "zero"]
    assert names(measures.filter(amount__in=[d("0.00"), d("1.005")])) == ["zero"]
    assert names(measures.exclude(amount__in=[d("0.00"), d("1.005")])) == [
        "high", "negative", "null", "rounded", "truncated",
    ]  # fmt: skip
    assert names(measures.filter(amount__range=(d("0.995"), d("1.005")))) == ["truncated"]
    assert names(measures.filter(amount=d("123456.789"))) == []
    assert names(measures.filter(amount__lt=d("123456.789"))) == [
        "high", "negative", "rounded", "truncated", "zero",
    ]  # fmt: skip
    assert names(measures.filter(amount=d("1E+5"))) == []
    assert names(measures.filter(amount=d("1.500"))) == []
    # Values that fit stay as they are.
    assert names(measures.filter(amount=d("1.00"))) == ["truncated"]
    assert names(measures.filter(small__in=[1, 32767])) == ["rounded", "truncated"]
    # More than 63 digits: a clear error, never truncated.
    with pytest.raises(NotSupportedError, match="at most 63"):
        list(measures.filter(amount=d(10**63)))
