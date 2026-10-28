"""Models used by the offline and IBM i tests."""

import datetime
import uuid
from decimal import Decimal

from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=100)


class Book(models.Model):
    id = models.BigAutoField(primary_key=True)
    author = models.ForeignKey(Author, models.CASCADE)
    title = models.CharField(max_length=200, db_index=True)
    published = models.DateTimeField(null=True)
    reading_time = models.TimeField(null=True)
    available = models.BooleanField(default=True)
    pages = models.PositiveIntegerField(default=0)


class Node(models.Model):
    id = models.SmallAutoField(primary_key=True)
    parent = models.ForeignKey("self", models.CASCADE, null=True)


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    label = models.SlugField(unique=True)


class Document(models.Model):
    """Long values: TextField (NCLOB) and BinaryField (BLOB)."""

    text = models.TextField()
    data = models.BinaryField(null=True)


class Defaults(models.Model):
    """One db_default per literal rule of DatabaseSchemaEditor.prepare_default()."""

    text = models.CharField(max_length=20, db_default="O'Brien 100%")
    flag = models.BooleanField(db_default=True)
    number = models.IntegerField(db_default=-1)
    amount = models.DecimalField(max_digits=5, decimal_places=2, db_default=Decimal("1.50"))
    ratio = models.FloatField(db_default=1.5)
    day = models.DateField(db_default=datetime.date(2026, 1, 2))
    clock = models.TimeField(db_default=datetime.time(13, 45, 30))
    stamp = models.DateTimeField(
        db_default=datetime.datetime(2026, 1, 2, 13, 45, 30, 123456, tzinfo=datetime.UTC)
    )
    data = models.BinaryField(db_default=b"\x01\xab")
    code = models.UUIDField(db_default=uuid.UUID("12345678-1234-5678-1234-567812345678"))
    nothing = models.IntegerField(null=True, db_default=None)


class Schedule(models.Model):
    """Date/time columns and a DurationField (BIGINT microseconds)."""

    start = models.DateTimeField(null=True)
    day = models.DateField(null=True)
    clock = models.TimeField(null=True)
    length = models.DurationField(null=True)


class Code(models.Model):
    """A CharField primary key (foreign keys to it are NVARCHAR)."""

    code = models.CharField(max_length=8, primary_key=True)


class Profile(models.Model):
    """A OneToOneField primary key: a key to a key (Author.id, INTEGER)."""

    author = models.OneToOneField(Author, models.CASCADE, primary_key=True)


class Link(models.Model):
    """Foreign keys to an integer, CharField, UUID and key primary key; an IP."""

    author = models.ForeignKey(Author, models.CASCADE, null=True)
    code = models.ForeignKey(Code, models.CASCADE, null=True)
    tag = models.ForeignKey(Tag, models.CASCADE, null=True)
    profile = models.ForeignKey(Profile, models.CASCADE, null=True)
    ip = models.GenericIPAddressField(null=True)


class Account(models.Model):
    """The target of a two-column relation (company, number)."""

    company = models.CharField(max_length=1)
    number = models.IntegerField()

    class Meta:
        unique_together = (("company", "number"),)


class Contact(models.Model):
    """A ForeignObject over two columns: Django filters it with (a, b) IN (...)."""

    company = models.CharField(max_length=1)
    account_number = models.IntegerField(null=True)
    account = models.ForeignObject(
        Account,
        models.CASCADE,
        from_fields=["company", "account_number"],
        to_fields=["company", "number"],
        related_name="contacts",
    )


class Switch(models.Model):
    """A nullable BooleanField: TRUE, FALSE and NULL rows."""

    name = models.CharField(max_length=10)
    flag = models.BooleanField(null=True)


class Measure(models.Model):
    """Numeric columns whose marker size a filter value can exceed (issue #69)."""

    small = models.SmallIntegerField(null=True)
    amount = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    big = models.BigIntegerField(null=True)


class Rating(models.Model):
    """CHECK constraints: a column check (PositiveSmallIntegerField) and model
    CheckConstraints comparing two columns and with string literals."""

    stars = models.PositiveSmallIntegerField()
    low = models.IntegerField(default=0)
    high = models.IntegerField(default=0)
    grade = models.CharField(max_length=2, default="A")

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(low__lte=models.F("high")),
                name="testapp_rating_low_lte_high",
            ),
            models.CheckConstraint(
                condition=models.Q(grade__in=["A", "B", "O'"]),
                name="testapp_rating_grade",
            ),
        )


# Issue #23: a model with an abstract base used as a mixin and an abstract
# base class. Django orders a model's fields by Field.creation_counter (the
# order the field objects were created in), not by the order of the bases:
# the inherited fields are copies that keep their counters. CREATE TABLE
# must follow _meta.local_fields exactly.
class TimestampedMixin(models.Model):
    created = models.DateTimeField(null=True)

    class Meta:
        abstract = True


class TitledBase(models.Model):
    title = models.CharField(max_length=50)
    subtitle = models.CharField(max_length=50, blank=True)

    class Meta:
        abstract = True


class Article(TimestampedMixin, TitledBase):
    body = models.CharField(max_length=100)
    rank = models.IntegerField(default=0)
