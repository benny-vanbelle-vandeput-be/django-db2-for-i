"""Can a comment with text outside the job CCSID reach Db2 for i? (``supports_comments``)

Decision 2026-10-26 keeps ``supports_comments`` off: ``COMMENT ON ... IS '<text>'``
rejects text outside the job CCSID (``€``, an emoji) with SQL0104, and
``UX'...'`` / ``N'...'`` constants are rejected too. This probe tries the other
routes, each with ``€`` and an emoji:

- ``COMMENT ON ... IS ?``: a parameter marker (Unicode from the driver);
- a dynamic compound statement that builds the ``COMMENT ON`` text in an
  ``NVARCHAR`` variable (``UX'...'`` is accepted in an expression) and runs it
  with ``EXECUTE IMMEDIATE``, and with ``PREPARE`` / ``EXECUTE``;
- ``LABEL ON`` (the 50-character text), the same ways;
- the control: plain text in the job CCSID.

Where a route is accepted, the comment is read back where Db2 for i shows it for
QTEMP, if anywhere (``QSYS2.SYSTABLES`` / ``SYSCOLUMNS``; probe 25 found nothing
there), and the object text (``LABEL ON TABLE``) through
``QSYS2.OBJECT_STATISTICS``, also as hex. A route that is accepted but cannot be
read back here needs an own IBM i test in a library to check the stored text.

Writes only to QTEMP (one table that disappears with the job); reads only the
catalog views. Without commitment control (CMT=0). One connection, one
statement per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- comment_unicode

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PCMTU"
TEXTS = (
    ("job CCSID", "Price", "'Price'"),
    ("euro", "Price in €", "'Price in ' CONCAT UX'20AC'"),
    ("emoji", "Smile \U0001f600", "'Smile ' CONCAT UX'D83DDE00'"),
)
TARGETS = (
    ("COMMENT ON TABLE", f"COMMENT ON TABLE {TABLE} IS"),
    ("COMMENT ON COLUMN", f"COMMENT ON COLUMN {TABLE}.A IS"),
    ("LABEL ON TABLE", f"LABEL ON TABLE {TABLE} IS"),
)


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _compound(target: str, expression: str, *, prepare: bool) -> str:
    """A dynamic compound statement that runs ``<target> '<text>'`` from an
    NVARCHAR variable; the text is built with ``UX'...'`` constants, so the
    statement text itself stays in the job CCSID."""
    build = f"SET S = '{target} ''' CONCAT {expression} CONCAT '''';"
    run = "PREPARE P FROM S; EXECUTE P;" if prepare else "EXECUTE IMMEDIATE S;"
    return f"BEGIN DECLARE S NVARCHAR(1000); {build} {run} END"


def _read_back(conn, results, label: str) -> None:
    _step(
        results,
        f"{label}: read SYSTABLES",
        _query(
            conn,
            "SELECT TABLE_TEXT, LONG_COMMENT FROM QSYS2.SYSTABLES "
            "WHERE TABLE_SCHEMA = 'QTEMP' AND TABLE_NAME = 'PCMTU'",
        ),
    )
    _step(
        results,
        f"{label}: read SYSCOLUMNS",
        _query(
            conn,
            "SELECT LONG_COMMENT FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = 'QTEMP' AND TABLE_NAME = 'PCMTU'",
        ),
    )
    _step(
        results,
        f"{label}: read the object text",
        _query(
            conn,
            "SELECT OBJTEXT, HEX(OBJTEXT), HEX(CAST(OBJTEXT AS NVARCHAR(50))) "
            "FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE', 'PCMTU'))",
        ),
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table, gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(results, "create", _execute(conn, f"CREATE TABLE {TABLE} (A INTEGER)"))
    if created["result"] != "ok":
        return results
    for target_name, target in TARGETS:
        print(f" -- {target_name}")
        for text_name, text, expression in TEXTS:
            key = f"{target_name}, {text_name}"
            _step(results, f"{key}: literal", _execute(conn, f"{target} {_literal(text)}"))
            _step(results, f"{key}: marker", _execute(conn, f"{target} ?", [text]))
            _step(
                results,
                f"{key}: EXECUTE IMMEDIATE",
                _execute(conn, _compound(target, expression, prepare=False)),
            )
            _step(
                results,
                f"{key}: PREPARE / EXECUTE",
                _execute(conn, _compound(target, expression, prepare=True)),
            )
            _read_back(conn, results, key)
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
