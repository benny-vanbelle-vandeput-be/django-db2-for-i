"""A nullable BooleanField used as a condition, by every path Django has, on
TRUE, FALSE and NULL rows.

Shared by the offline reference test, which runs them on SQLite (Django on a
backend with standard three-valued logic), and by the IBM i test, which runs
them on IBM i. Django renders ``filter(flag=True/False)`` through Exact's
boolean shortcut (``flag`` / ``NOT flag``) and ``~F("flag")`` as a
NegatedExpression; Db2 for i's NOT of a BOOLEAN value treats NULL as false.
"""

from __future__ import annotations

from django.db.models import BooleanField, Case, ExpressionWrapper, F, Q, QuerySet, Value, When

from tests.testapp.models import Switch

SWITCHES = (("t", True), ("f", False), ("n", None))


def create(using: str) -> None:
    for name, flag in SWITCHES:
        Switch.objects.using(using).create(name=name, flag=flag)


def querysets(using: str) -> dict[str, QuerySet]:
    switches = Switch.objects.using(using)
    names = lambda queryset: queryset.values_list("name", flat=True)  # noqa: E731
    case = lambda condition: switches.annotate(  # noqa: E731
        x=Case(When(condition, then=Value(1)), default=Value(0))
    ).values_list("name", "x")
    flag_value = ExpressionWrapper(F("flag"), output_field=BooleanField())
    known = switches.annotate(
        known=Case(
            When(name="t", then=Value(True)),
            When(name="f", then=Value(False)),
            default=Value(None),
            output_field=BooleanField(),
        )
    )
    return {
        "filter(flag=True)": names(switches.filter(flag=True)),
        "filter(flag=False)": names(switches.filter(flag=False)),
        "exclude(flag=True)": names(switches.exclude(flag=True)),
        "exclude(flag=False)": names(switches.exclude(flag=False)),
        "filter(~Q(flag=True))": names(switches.filter(~Q(flag=True))),
        "filter(~Q(flag=False))": names(switches.filter(~Q(flag=False))),
        "filter(flag as a condition)": names(switches.filter(flag_value)),
        "filter(~F(flag))": names(switches.filter(~F("flag"))),
        "exclude(flag as a condition)": names(switches.exclude(flag_value)),
        "exclude(~F(flag))": names(switches.exclude(~F("flag"))),
        "filter(Q(flag=True) | Q(name=n))": names(switches.filter(Q(flag=True) | Q(name="n"))),
        "filter(~F(flag) & ~Q(name=t))": names(switches.filter(~F("flag") & ~Q(name="t"))),
        "When(Q(flag=True))": case(Q(flag=True)),
        "When(Q(flag=False))": case(Q(flag=False)),
        "When(~Q(flag=True))": case(~Q(flag=True)),
        "When(~F(flag))": case(~F("flag")),
        "annotate(neg=~F(flag)).filter(neg=True)": names(
            switches.annotate(neg=~F("flag")).filter(neg=True)
        ),
        "annotate(neg=~F(flag)).filter(neg=False)": names(
            switches.annotate(neg=~F("flag")).filter(neg=False)
        ),
        "annotate(neg=~F(flag)).exclude(neg=True)": names(
            switches.annotate(neg=~F("flag")).exclude(neg=True)
        ),
        "annotate(b=F(flag)).filter(b=False)": names(
            switches.annotate(b=F("flag")).filter(b=False)
        ),
        "Case annotation .filter(known=False)": names(known.filter(known=False)),
        "Case annotation .exclude(known=True)": names(known.exclude(known=True)),
        "filter(flag=~Value(True))": names(switches.filter(flag=~Value(True))),
        "selected ~F(flag)": switches.annotate(neg=~F("flag")).values_list("name", "neg"),
        "selected Q(flag=True)": switches.annotate(b=Q(flag=True)).values_list("name", "b"),
        "selected Q(flag=False)": switches.annotate(b=Q(flag=False)).values_list("name", "b"),
        "selected ~Q(flag=True)": switches.annotate(b=~Q(flag=True)).values_list("name", "b"),
        "selected Q(flag=True) | Q(name=f)": switches.annotate(
            b=Q(flag=True) | Q(name="f")
        ).values_list("name", "b"),
    }


def rows(queryset: QuerySet) -> list:
    return sorted(queryset, key=repr)


# The reference: Django with native-boolean SQL (has_native_boolean_field, as on
# PostgreSQL) evaluated by SQLite's three-valued logic
# (tests/offline/test_boolean_reference.py checks it). The NULL row: no
# positive filter matches it; exclude(flag=True) keeps it because Django adds
# "AND flag IS NOT NULL" for a nullable column (also inside a selected ~Q); a
# selected ~F("flag") or Q(flag=...) is None.
EXPECTED: dict[str, list] = {
    "filter(flag=True)": ["t"],
    "filter(flag=False)": ["f"],
    "exclude(flag=True)": ["f", "n"],
    "exclude(flag=False)": ["n", "t"],
    "filter(~Q(flag=True))": ["f", "n"],
    "filter(~Q(flag=False))": ["n", "t"],
    "filter(flag as a condition)": ["t"],
    "filter(~F(flag))": ["f"],
    "exclude(flag as a condition)": ["f"],
    "exclude(~F(flag))": ["t"],
    "filter(Q(flag=True) | Q(name=n))": ["n", "t"],
    "filter(~F(flag) & ~Q(name=t))": ["f"],
    "When(Q(flag=True))": [("f", 0), ("n", 0), ("t", 1)],
    "When(Q(flag=False))": [("f", 1), ("n", 0), ("t", 0)],
    "When(~Q(flag=True))": [("f", 1), ("n", 1), ("t", 0)],
    "When(~F(flag))": [("f", 1), ("n", 0), ("t", 0)],
    "annotate(neg=~F(flag)).filter(neg=True)": ["f"],
    "annotate(neg=~F(flag)).filter(neg=False)": ["t"],
    "annotate(neg=~F(flag)).exclude(neg=True)": ["t"],
    "annotate(b=F(flag)).filter(b=False)": ["f"],
    "Case annotation .filter(known=False)": ["f"],
    "Case annotation .exclude(known=True)": ["f"],
    "filter(flag=~Value(True))": ["f"],
    "selected ~F(flag)": [("f", True), ("n", None), ("t", False)],
    "selected Q(flag=True)": [("f", False), ("n", None), ("t", True)],
    "selected Q(flag=False)": [("f", True), ("n", None), ("t", False)],
    "selected ~Q(flag=True)": [("f", True), ("n", True), ("t", False)],
    "selected Q(flag=True) | Q(name=f)": [("f", True), ("n", None), ("t", True)],
}
