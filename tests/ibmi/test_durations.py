"""Durations against the IBM i: DurationField (BIGINT microseconds), timedelta
values and date/time +/- duration arithmetic (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt

import pytest
from django.db.models import DurationField, ExpressionWrapper, F, Value

from tests.testapp.models import Schedule

pytestmark = pytest.mark.usefixtures("testapp_tables")

UTC = dt.UTC
LONG = dt.timedelta(days=40 * 365 + 10, microseconds=7)  # beyond 10**15 microseconds
LENGTHS = [
    dt.timedelta(microseconds=1),
    dt.timedelta(days=-3, hours=5, microseconds=999999),  # negative
    dt.timedelta(days=75, hours=25, minutes=3),  # several months
    LONG,
    # The largest DurationField value: BIGINT microseconds (timedelta.max does not fit).
    dt.timedelta(microseconds=2**63 - 1),
]


def test_duration_values_round_trip(live, empty) -> None:
    for length in LENGTHS:
        Schedule.objects.create(length=length)
    assert list(Schedule.objects.order_by("id").values_list("length", flat=True)) == LENGTHS
    assert Schedule.objects.filter(length__lt=dt.timedelta(0)).count() == 1
    assert Schedule.objects.filter(length__gt=LONG).count() == 1
    assert Schedule.objects.filter(length=LENGTHS[2]).count() == 1


def test_datetime_plus_and_minus_durations(live, empty) -> None:
    start = dt.datetime(2026, 1, 31, 23, 0, 0, 1, tzinfo=UTC)
    for length in LENGTHS[:4]:
        Schedule.objects.create(start=start, length=length)
    rows = Schedule.objects.order_by("id").values_list(
        F("start") + F("length"), F("start") - F("length")
    )
    assert list(rows) == [(start + length, start - length) for length in LENGTHS[:4]]
    # A filter against an end time computed in SQL (several months, > 31.7 years).
    end = F("start") + F("length")
    assert Schedule.objects.filter(start__lt=end).count() == 3
    later = start + dt.timedelta(days=60)
    assert Schedule.objects.filter(start__lt=Value(later) - F("length")).count() == 2


def test_durations_near_year_1_and_9999(live, empty) -> None:
    first = dt.datetime(1, 1, 1, tzinfo=UTC)
    last = dt.datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
    Schedule.objects.create(start=first, length=dt.timedelta(days=1, microseconds=1))
    Schedule.objects.create(start=last, length=dt.timedelta(days=-1, microseconds=-1))
    span = last - first  # the whole timestamp range, far beyond 10**15 microseconds
    Schedule.objects.create(start=first, length=span)
    rows = Schedule.objects.order_by("id").values_list(F("start") + F("length"), flat=True)
    assert list(rows) == [
        dt.datetime(1, 1, 2, 0, 0, 0, 1, tzinfo=UTC),
        dt.datetime(9999, 12, 30, 23, 59, 59, 999998, tzinfo=UTC),
        last,
    ]


def test_date_and_time_plus_durations(live, empty) -> None:
    length = dt.timedelta(days=40, hours=25, microseconds=7)
    Schedule.objects.create(day=dt.date(2026, 1, 31), clock=dt.time(23, 30), length=length)
    row = Schedule.objects.values(
        day_end=F("day") + F("length"), clock_end=F("clock") + F("length")
    ).get()
    # DateField + DurationField is a DateTimeField; TimeField + DurationField wraps
    # at 24 hours and has no fractions on Db2 for i.
    assert row == {
        "day_end": dt.datetime(2026, 3, 13, 1, 0, 0, 7, tzinfo=UTC),
        "clock_end": dt.time(0, 30),
    }


def test_duration_times_and_divided_by_numbers(live, empty) -> None:
    Schedule.objects.create(length=dt.timedelta(days=10, microseconds=5))
    times = ExpressionWrapper(F("length") * 3, output_field=DurationField())
    half = ExpressionWrapper(F("length") / 2, output_field=DurationField())
    assert Schedule.objects.values_list(times, half).get() == (
        dt.timedelta(days=30, microseconds=15),
        dt.timedelta(days=5, microseconds=2),
    )
    Schedule.objects.update(length=F("length") + Value(dt.timedelta(days=-20)))
    assert Schedule.objects.values_list("length", flat=True).get() == dt.timedelta(
        days=-10, microseconds=5
    )


def test_temporal_subtraction(live, empty) -> None:
    """supports_temporal_subtraction: exact microseconds with DAYS(),
    MIDNIGHT_SECONDS() and MICROSECOND() (never TIMESTAMPDIFF, which assumes
    30-day months): several months and years, negative results, year 1 to
    9999, DateField - DateField and TimeField - TimeField."""
    cases = [
        # (start, day, clock), compared with the first row
        (
            dt.datetime(2026, 1, 31, 1, 0, 0, 2, tzinfo=UTC),
            dt.date(2026, 2, 28),
            dt.time(18, 30, 15),
        ),
        (
            dt.datetime(2026, 3, 31, 23, 0, 0, 1, tzinfo=UTC),
            dt.date(2026, 5, 31),
            dt.time(23, 59, 59),
        ),
        (dt.datetime(2019, 2, 28, 0, 0, 0, 500000, tzinfo=UTC), dt.date(2001, 1, 1), dt.time(6, 0)),
        (dt.datetime(1, 1, 1, tzinfo=UTC), dt.date(1, 1, 1), dt.time(0, 0)),
        (
            dt.datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
            dt.date(9999, 12, 31),
            dt.time(0, 0, 1),
        ),
    ]
    for start, day, clock in cases:
        Schedule.objects.create(start=start, day=day, clock=clock)
    first = Schedule.objects.order_by("id").first()
    rows = Schedule.objects.order_by("id").values_list(
        F("start") - Value(first.start),
        F("day") - Value(first.day),
        F("clock") - Value(first.clock),
    )
    base = dt.date(2000, 1, 1)
    expected = [
        (
            start - first.start,
            day - first.day,
            dt.datetime.combine(base, clock) - dt.datetime.combine(base, first.clock),
        )
        for start, day, clock in cases
    ]
    assert list(rows) == expected
    # A filter on a computed duration (rows more than 60 days after the first).
    later = Schedule.objects.filter(start__gt=first.start).annotate(
        gap=F("start") - Value(first.start)
    )
    assert later.filter(gap__gt=dt.timedelta(days=60)).count() == 1
    # Subtraction between two columns of the same row.
    assert set(Schedule.objects.values_list(F("start") - F("start"), flat=True)) == {
        dt.timedelta(0)
    }


def test_out_of_range_durations_are_refused_on_every_path(live, empty) -> None:
    """A duration beyond BIGINT microseconds raises the backend's ValueError before
    anything is sent, on every path that prepares a DurationField value: create,
    update(), save(), bulk_update() (Case/When), a filter and Value(). On Django
    before 6.1 through compat.install_duration_adapter(); the rows stay unchanged."""
    too_long = dt.timedelta(microseconds=2**63)
    fits = Schedule.objects.create(length=LENGTHS[0])
    refused = "does not fit a DurationField"
    with pytest.raises(ValueError, match=refused):
        Schedule.objects.create(length=too_long)
    with pytest.raises(ValueError, match=refused):
        Schedule.objects.filter(pk=fits.pk).update(length=too_long)
    fits.length = too_long
    with pytest.raises(ValueError, match=refused):
        fits.save()
    with pytest.raises(ValueError, match=refused):
        Schedule.objects.bulk_update([fits], ["length"])
    with pytest.raises(ValueError, match=refused):
        list(Schedule.objects.filter(length__lt=too_long))
    with pytest.raises(ValueError, match=refused):
        list(Schedule.objects.annotate(x=Value(too_long, output_field=DurationField())))
    assert list(Schedule.objects.values_list("length", flat=True)) == [LENGTHS[0]]
