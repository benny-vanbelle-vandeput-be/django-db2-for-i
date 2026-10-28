"""Values of relations and IP addresses against the IBM i: bulk_update (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import uuid

import pytest

from tests.testapp.models import Author, Code, Link, Profile, Tag

pytestmark = pytest.mark.usefixtures("testapp_tables")


def test_bulk_update_foreign_keys_and_ip_addresses(live, empty) -> None:
    """bulk_update writes CASE WHEN ... THEN <value> with each ForeignKey value
    typed as its target: integer, CharField and UUID primary keys, and a key to
    a key (Profile's primary key is a OneToOneField to Author)."""
    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    code = Code.objects.create(code="X-1")
    tag = Tag.objects.create(id=uuid.UUID("12345678-1234-5678-1234-567812345678"), label="t")
    profile = Profile.objects.create(author=other)
    first, second = Link.objects.create(), Link.objects.create(author=author, ip="1.2.3.4")
    first.author, first.code, first.tag, first.profile, first.ip = (
        other,
        code,
        tag,
        profile,
        "2001::1",
    )
    second.author, second.ip = None, None
    Link.objects.bulk_update([first, second], ["author", "code", "tag", "profile", "ip"])
    rows = Link.objects.order_by("id").values_list("author", "code", "tag", "profile", "ip")
    assert list(rows) == [
        (other.pk, "X-1", tag.pk, other.pk, "2001::1"),
        (None, None, None, None, None),
    ]
    assert Link.objects.filter(tag=tag, code__code="X-1", profile__author=other).count() == 1
