"""Lookups on a multi-column relation (Contact.account, a two-column
ForeignObject) in every context, with a NULL in one column.

Shared by the offline reference test, which runs them on SQLite (a backend
with supports_tuple_lookups and standard row-value semantics), and by the
pub400 test, which runs them on IBM i. EXPECTED holds the reference rows;
KNOWN_DIFFERENCES lists where the backend differs, with the reason.
"""

from __future__ import annotations

from django.db.models import Case, Q, QuerySet, Value, When

from tests.testapp.models import Account, Contact

ACCOUNTS = (("a", 1), ("b", 2), ("c", 3))
CONTACTS = (("a", 1), ("a", None), ("b", 2), ("b", 1), ("c", 9))


def create(using: str) -> None:
    for company, number in ACCOUNTS:
        Account.objects.using(using).create(company=company, number=number)
    for company, number in CONTACTS:
        Contact.objects.using(using).create(company=company, account_number=number)


def conditions(using: str) -> dict[str, Q]:
    accounts = Account.objects.using(using)
    a1 = accounts.get(company="a", number=1)
    b2 = accounts.get(company="b", number=2)
    return {
        "in_subquery": Q(account__in=accounts.filter(number__lte=2)),
        "in_list": Q(account__in=[a1, b2]),
        "exact": Q(account=a1),
        "gt": Q(account__gt=a1),
    }


def querysets(using: str) -> dict[str, QuerySet]:
    """``<condition>/<context>`` -> a values_list queryset."""
    contacts = Contact.objects.using(using)
    columns = ("company", "account_number")
    result = {}
    for name, condition in conditions(using).items():
        result[f"{name}/filter"] = contacts.filter(condition).values_list(*columns)
        result[f"{name}/exclude"] = contacts.exclude(condition).values_list(*columns)
        result[f"{name}/not_q"] = contacts.filter(~condition).values_list(*columns)
        result[f"{name}/xor"] = contacts.filter(condition ^ Q(company="c")).values_list(*columns)
        result[f"{name}/selected"] = contacts.annotate(v=condition).values_list(*columns, "v")
        result[f"{name}/when"] = contacts.annotate(
            v=Case(When(condition, then=Value(1)), default=Value(0))
        ).values_list(*columns, "v")
    return result


def rows(queryset: QuerySet) -> list[tuple]:
    return sorted(queryset, key=repr)


# The reference: SQLite with supports_tuple_lookups (tests/offline/test_tuple_reference.py
# checks it). ``("a", NULL)`` is UNKNOWN for every condition: no filter, exclude
# or ~Q returns it; as a selected value it is None.
EXPECTED: dict[str, list[tuple]] = {
    "in_subquery/filter": [("a", 1), ("b", 2)],
    "in_subquery/exclude": [("b", 1), ("c", 9)],
    "in_subquery/not_q": [("b", 1), ("c", 9)],
    "in_subquery/xor": [("a", 1), ("b", 2), ("c", 9)],
    "in_subquery/selected": [
        ("a", 1, True),
        ("a", None, None),
        ("b", 1, False),
        ("b", 2, True),
        ("c", 9, False),
    ],
    "in_subquery/when": [("a", 1, 1), ("a", None, 0), ("b", 1, 0), ("b", 2, 1), ("c", 9, 0)],
    "in_list/filter": [("a", 1), ("b", 2)],
    "in_list/exclude": [("b", 1), ("c", 9)],
    "in_list/not_q": [("b", 1), ("c", 9)],
    "in_list/xor": [("a", 1), ("b", 2), ("c", 9)],
    "in_list/selected": [
        ("a", 1, True),
        ("a", None, None),
        ("b", 1, False),
        ("b", 2, True),
        ("c", 9, False),
    ],
    "in_list/when": [("a", 1, 1), ("a", None, 0), ("b", 1, 0), ("b", 2, 1), ("c", 9, 0)],
    "exact/filter": [("a", 1)],
    "exact/exclude": [("b", 1), ("b", 2), ("c", 9)],
    "exact/not_q": [("b", 1), ("b", 2), ("c", 9)],
    "exact/xor": [("a", 1), ("c", 9)],
    "exact/selected": [
        ("a", 1, True),
        ("a", None, None),
        ("b", 1, False),
        ("b", 2, False),
        ("c", 9, False),
    ],
    "exact/when": [("a", 1, 1), ("a", None, 0), ("b", 1, 0), ("b", 2, 0), ("c", 9, 0)],
    "gt/filter": [("b", 1), ("b", 2), ("c", 9)],
    "gt/exclude": [("a", 1)],
    "gt/not_q": [("a", 1)],
    "gt/xor": [("b", 1), ("b", 2)],
    "gt/selected": [
        ("a", 1, False),
        ("a", None, None),
        ("b", 1, True),
        ("b", 2, True),
        ("c", 9, True),
    ],
    "gt/when": [("a", 1, 0), ("a", None, 0), ("b", 1, 1), ("b", 2, 1), ("c", 9, 1)],
}


def _unknown_as_false(expected: list[tuple]) -> list[tuple]:
    return sorted(((*row[:-1], False) if row[-1] is None else row for row in expected), key=repr)


# Reason -> {name: the backend's rows}.
KNOWN_DIFFERENCES: dict[str, dict[str, list[tuple]]] = {
    "issue #75: a selected UNKNOWN predicate is False, not None": {
        name: _unknown_as_false(expected)
        for name, expected in EXPECTED.items()
        if name.endswith("/selected")
    },
}
