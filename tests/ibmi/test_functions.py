"""Database functions against the IBM i (phase 6, PR 1): the functions whose SQL
differs from Django's default, on querysets with model instances (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import hashlib
import math
from decimal import Decimal

import pytest
from django.db import NotSupportedError, models
from django.db.models import Count, F, Value
from django.db.models.functions import (
    MD5,
    SHA1,
    SHA256,
    SHA384,
    SHA512,
    ATan2,
    Cast,
    Chr,
    Concat,
    Length,
    Log,
    LPad,
    Ord,
    Repeat,
    Reverse,
    Upper,
)

from django_db2_for_i import compat
from tests.testapp.models import Author, Book, Document, Tag

pytestmark = pytest.mark.usefixtures("testapp_tables")

NAMES = ["Élena", "zoë 😀", "plain"]


def test_text_functions_on_non_ascii_names(live, empty) -> None:
    """Length counts characters (an emoji is one), the hashes match Python's
    hashlib over UTF-8, and they can be filtered and ordered by."""
    for name in NAMES:
        Author.objects.create(name=name)
    authors = Author.objects.annotate(
        n=Length("name"),
        md5=MD5("name"),
        sha1=SHA1("name"),
        sha256=SHA256("name"),
        sha512=SHA512("name"),
    )
    assert sorted((a.name, a.n) for a in authors) == [("plain", 5), ("zoë 😀", 5), ("Élena", 5)]
    for author in authors:
        data = author.name.encode()
        assert author.md5 == hashlib.md5(data).hexdigest()
        assert author.sha1 == hashlib.sha1(data).hexdigest()
        assert author.sha256 == hashlib.sha256(data).hexdigest()
        assert author.sha512 == hashlib.sha512(data).hexdigest()
    digest = hashlib.md5("zoë 😀".encode()).hexdigest()
    assert list(Author.objects.annotate(h=MD5("name")).filter(h=digest)) == [
        Author.objects.get(name="zoë 😀")
    ]
    assert Author.objects.annotate(n=Length("name")).filter(n=5).count() == 3


def test_hash_of_a_long_text_field(live, empty) -> None:
    """A TextField (NCLOB) beyond NVARCHAR's limits is hashed as UTF-8 too."""
    text = "é" * 20_000 + "😀"
    document = Document.objects.create(text=text)
    row = Document.objects.annotate(h=SHA256("text"), n=Length("text")).get(pk=document.pk)
    assert row.h == hashlib.sha256(text.encode()).hexdigest()
    assert row.n == 20_001


def test_chr_and_ord_beyond_ascii(live, empty) -> None:
    """Through UTF-16, with a surrogate pair above U+FFFF (probe qtemp_supplementary_chars):
    on a CharField (NVARCHAR), a TextField (NCLOB), and back with Chr."""
    texts = ["Élena", "😀 smile", "x😀", "plain", ""]
    for text in texts:
        Author.objects.create(name=text)
        Document.objects.create(text=text)
    authors = Author.objects.annotate(code=Ord("name")).order_by("pk")
    assert [a.code for a in authors] == [ord(t[0]) if t else 0 for t in texts]
    documents = Document.objects.annotate(code=Ord("text")).order_by("pk")
    assert [d.code for d in documents] == [ord(t[0]) if t else 0 for t in texts]
    back = Author.objects.exclude(name="").annotate(first=Chr(Ord("name"))).order_by("pk")
    assert [a.first for a in back] == [t[0] for t in texts if t]
    assert Author.objects.filter(name__startswith=Chr(Value(0x1F600))).count() == 1


@pytest.mark.skipif(compat.UUID4 is None, reason="UUID4() is new in Django 6.1")
def test_uuid4_fills_uuid_fields(live, empty) -> None:
    """UUID4() through GENERATE_UUID(), detected at connect (probe phase7_flags):
    version 4, distinct, and found again by the value Django reads back."""
    assert live.features.supports_uuid4_function is True
    for name in ("a", "b", "c"):
        Tag.objects.create(label=name)
    before = set(Tag.objects.values_list("id", flat=True))
    Tag.objects.update(id=compat.UUID4())
    tags = list(Tag.objects.all())
    assert len({tag.id for tag in tags}) == 3
    assert all(tag.id.version == 4 for tag in tags)
    assert not before & {tag.id for tag in tags}
    assert Tag.objects.get(id=tags[0].id).label == tags[0].label


def test_functions_db2_for_i_lacks_raise(live, empty) -> None:
    Author.objects.create(name="a")
    for function in (Reverse, SHA384):
        with pytest.raises(NotSupportedError):
            list(Author.objects.annotate(x=function("name")))


def test_concat_over_a_left_join_treats_null_as_empty(live, empty) -> None:
    """Concat of a name and the title of a book that does not exist (LEFT JOIN)
    keeps the name, as on Django's other backends."""
    author = Author.objects.create(name="Élena")
    nobody = Author.objects.create(name="zoë")
    Book.objects.create(author=author, title="één", pages=3)
    rows = Author.objects.annotate(
        label=Concat("name", Value(": "), Upper("book__title"), output_field=models.TextField())
    ).order_by("id")
    assert [(a, a.label) for a in rows] == [(author, "Élena: ÉÉN"), (nobody, "zoë: ")]


def test_padding_and_repeating_with_null(live, empty) -> None:
    author = Author.objects.create(name="ab")
    row = Author.objects.annotate(
        left=LPad("name", 5, Value("·")),
        none=LPad(Value(None), 3),
        twice=Repeat("name", 2),
        never=Repeat("name", None),
    ).get(pk=author.pk)
    assert (row.left, row.none, row.twice, row.never) == ("···ab", None, "abab", None)


def test_math_functions_argument_order(live, empty) -> None:
    """Log(base, x) and ATan2(y, x) in Django's order (Db2 for i's LOG takes one
    argument and its ATAN2 takes x first)."""
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="t", pages=8)
    row = Book.objects.annotate(
        log=Log(Value(2.0), Cast("pages", models.FloatField())),
        angle=ATan2(Value(1.0), Cast("pages", models.FloatField())),
    ).get()
    assert row.log == pytest.approx(3.0)
    assert row.angle == pytest.approx(math.atan2(1, 8))


def test_cast_to_a_decimal_rounds(live, empty) -> None:
    """A number cast to a DecimalField is rounded, halves away from zero, where
    Db2 for i's CAST alone cuts off."""
    author = Author.objects.create(name="a")
    for pages in (5, 10):
        Book.objects.create(author=author, title="t", pages=pages)
    third = Cast(F("pages") / Value(3.0), models.DecimalField(max_digits=6, decimal_places=2))
    half = Cast(F("pages") / Value(2.0), models.DecimalField(max_digits=6, decimal_places=0))
    rows = Book.objects.annotate(third=third, half=half).order_by("pages")
    assert [(b.pages, b.third, b.half) for b in rows] == [
        (5, Decimal("1.67"), Decimal("3")),
        (10, Decimal("3.33"), Decimal("5")),
    ]


def test_cast_of_a_float_to_text(live, empty) -> None:
    """A float cast to text reads as on Django's other backends (3, 4.5, 300),
    not in Db2 for i's exponent notation (3E0), and can be filtered by."""
    author = Author.objects.create(name="a")
    for pages in (6, 9, 600):
        Book.objects.create(author=author, title="t", pages=pages)
    half = Cast(Cast("pages", models.FloatField()) / Value(2.0), models.CharField())
    rows = Book.objects.annotate(half=half).order_by("pages")
    assert [b.half for b in rows] == ["3", "4.5", "300"]
    assert Book.objects.annotate(half=half).filter(half="4.5").get().pages == 9


def test_group_by_a_text_field(live, empty) -> None:
    """allows_group_by_lob: values() over a TextField (NCLOB) with an aggregate."""
    long = "x" * 5_000
    for text in ("é", "é", long):
        Document.objects.create(text=text)
    groups = Document.objects.values("text").annotate(n=Count("id")).order_by("n")
    assert [(len(g["text"]), g["n"]) for g in groups] == [(5_000, 1), (1, 2)]


@pytest.mark.skipif(compat.StringAgg is None, reason="StringAgg requires Django 6.0+")
def test_string_agg_distinct(live, empty) -> None:
    from django.db.models import StringAgg

    author = Author.objects.create(name="a")
    for title in ("één", "two", "één"):
        Book.objects.create(author=author, title=title, pages=1)
    row = Author.objects.annotate(titles=StringAgg("book__title", Value(","), distinct=True)).get()
    assert sorted(row.titles.split(",")) == ["two", "één"]


def test_window_functions_over_model_instances(live, empty) -> None:
    """supports_over_clause: a ranking per author, LAG with an offset and a
    default, NTH_VALUE, PERCENT_RANK as a float, and a RANGE frame, on full
    querysets with model instances."""
    from django.db.models import Sum, ValueRange, Window
    from django.db.models.functions import Lag, NthValue, PercentRank, Rank

    first = Author.objects.create(name="Élena")
    second = Author.objects.create(name="zoë")
    for author, pages in ((first, 10), (first, 30), (first, 20), (second, 5), (second, 7)):
        Book.objects.create(author=author, title=f"t{pages}", pages=pages)
    per_author = {"partition_by": F("author"), "order_by": F("pages").asc()}
    books = Book.objects.annotate(
        rank=Window(Rank(), **per_author),
        previous=Window(Lag("pages", 1, default=Value(0)), **per_author),
        second=Window(NthValue("pages", 2), **per_author),
        share=Window(PercentRank(), **per_author),
        near=Window(Sum("pages"), order_by=F("pages").asc(), frame=ValueRange(start=-5, end=5)),
    ).order_by("author_id", "pages")
    rows = [(b.author, b.pages, b.rank, b.previous, b.second, b.share, b.near) for b in books]
    assert rows == [
        (first, 10, 1, 0, None, 0.0, 22),
        (first, 20, 2, 10, 20, 0.5, 20),
        (first, 30, 3, 20, 20, 1.0, 30),
        (second, 5, 1, 0, None, 0.0, 22),
        (second, 7, 2, 5, 7, 1.0, 22),
    ]
    assert all(isinstance(b.share, float) for b in books)
