"""JSON on Db2 for i, for phase 6 (``supports_json_field`` and its flags).

Writes only to QTEMP (tables that disappear with the job); reads nothing outside
it. Without commitment control (CMT=0): QTEMP tables have no journal, and a CHECK
constraint is refused there (SQL7008), so ``IS JSON`` is tried as a predicate; the
constraint itself needs a ``lib_`` probe. One connection, one statement per case,
no retries.

- **Which column type:** NCLOB (what ``TextField`` uses), CLOB CCSID 1208 and BLOB:
  round trip with non-ASCII text and the JSON functions on each.
- **Paths:** literal or parameter marker; quoted keys, array positions, a root
  array (IBM wraps it in SYSIBM_ROOT_ARRAY), negative positions.
- **Scalars at the top level** (``supports_primitives_in_json_field``).
- **JSON null against a missing key:** what Django's ``isnull`` and ``=None``
  lookups have to tell apart.
- **Building:** ``JSON_OBJECT`` and ``JSON_ARRAY`` with typed markers
  (``has_json_object_function``).
- **Containment:** whether anything serves ``contains`` / ``contained_by``.

Usage (inside the "tests" container):
    nox -s probe -- json_functions

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6JSON"
DOCUMENT = (
    '{"a": 1, "b": "téxt \U0001f600", "c": null, "d": [10, 20, 30], '
    '"e": {"f": true}, "g h": 2, "i": 1.5}'
)
COLUMN_TYPES = (("NCLOB", "NCLOB"), ("CLOB 1208", "CLOB(1M) CCSID 1208"), ("BLOB", "BLOB(1M)"))

ON_EACH_TYPE = (
    ("round trip", "SELECT C FROM {t}", ()),
    ("IS JSON", "SELECT CASE WHEN C IS JSON THEN 1 ELSE 0 END FROM {t}", ()),
    ("JSON_VALUE number", "SELECT JSON_VALUE(C, '$.a' RETURNING INTEGER) FROM {t}", ()),
    ("JSON_VALUE text", "SELECT JSON_VALUE(C, '$.b' RETURNING NVARCHAR(100)) FROM {t}", ()),
    ("JSON_VALUE default type", "SELECT JSON_VALUE(C, '$.b') FROM {t}", ()),
    ("JSON_QUERY object", "SELECT JSON_QUERY(C, '$.e') FROM {t}", ()),
    ("JSON_EXISTS", "SELECT CASE WHEN JSON_EXISTS(C, '$.a') THEN 1 ELSE 0 END FROM {t}", ()),
)
ON_NCLOB = (
    ("path as a marker", "SELECT JSON_VALUE(C, ?) FROM {t}", ("$.a",)),
    ("path as a typed marker", "SELECT JSON_VALUE(C, CAST(? AS VARCHAR(100))) FROM {t}", ("$.a",)),
    ("JSON_QUERY path as a marker", "SELECT JSON_QUERY(C, ?) FROM {t}", ("$.e",)),
    (
        "JSON_EXISTS path as a marker",
        "SELECT CASE WHEN JSON_EXISTS(C, ?) THEN 1 ELSE 0 END FROM {t}",
        ("$.a",),
    ),
    ("quoted key", """SELECT JSON_VALUE(C, '$."g h"' RETURNING INTEGER) FROM {t}""", ()),
    ("array position", "SELECT JSON_VALUE(C, '$.d[1]' RETURNING INTEGER) FROM {t}", ()),
    ("last array position", "SELECT JSON_VALUE(C, '$.d[last]' RETURNING INTEGER) FROM {t}", ()),
    ("negative array position", "SELECT JSON_VALUE(C, '$.d[-1]' RETURNING INTEGER) FROM {t}", ()),
    ("last minus one", "SELECT JSON_VALUE(C, '$.d[last-1]' RETURNING INTEGER) FROM {t}", ()),
    ("JSON_VALUE of an array", "SELECT JSON_VALUE(C, '$.d') FROM {t}", ()),
    ("JSON_QUERY of a scalar", "SELECT JSON_QUERY(C, '$.a') FROM {t}", ()),
    (
        "JSON_QUERY of a scalar, wrapper",
        "SELECT JSON_QUERY(C, '$.a' WITH CONDITIONAL WRAPPER) FROM {t}",
        (),
    ),
    ("JSON_QUERY of a string", "SELECT JSON_QUERY(C, '$.b' WITH CONDITIONAL WRAPPER) FROM {t}", ()),
    ("JSON_QUERY of an array", "SELECT JSON_QUERY(C, '$.d' WITH CONDITIONAL WRAPPER) FROM {t}", ()),
    ("JSON_VALUE of JSON null", "SELECT JSON_VALUE(C, '$.c'), JSON_VALUE(C, '$.z') FROM {t}", ()),
    (
        "JSON_EXISTS of JSON null and of a missing key",
        "SELECT CASE WHEN JSON_EXISTS(C, '$.c') THEN 1 ELSE 0 END, "
        "CASE WHEN JSON_EXISTS(C, '$.z') THEN 1 ELSE 0 END FROM {t}",
        (),
    ),
    (
        "JSON_QUERY of JSON null",
        "SELECT JSON_QUERY(C, '$.c' WITH CONDITIONAL WRAPPER) FROM {t}",
        (),
    ),
    ("JSON_VALUE boolean", "SELECT JSON_VALUE(C, '$.e.f') FROM {t}", ()),
    (
        "JSON_VALUE RETURNING BOOLEAN",
        "SELECT JSON_VALUE(C, '$.e.f' RETURNING BOOLEAN) FROM {t}",
        (),
    ),
    ("JSON_VALUE RETURNING DOUBLE", "SELECT JSON_VALUE(C, '$.i' RETURNING DOUBLE) FROM {t}", ()),
    ("JSON_VALUE of the wrong type", "SELECT JSON_VALUE(C, '$.b' RETURNING INTEGER) FROM {t}", ()),
    (
        "in WHERE, typed marker",
        "SELECT 1 FROM {t} WHERE JSON_VALUE(C, '$.a' RETURNING INTEGER) = ?",
        (1,),
    ),
    ("in ORDER BY", "SELECT 1 FROM {t} ORDER BY JSON_VALUE(C, '$.a' RETURNING INTEGER)", ()),
    (
        "in GROUP BY",
        "SELECT JSON_VALUE(C, '$.a' RETURNING INTEGER), COUNT(*) FROM {t} GROUP BY JSON_VALUE(C, "
        "'$.a' RETURNING INTEGER)",
        (),
    ),
    (
        "a filter in the path",
        "SELECT CASE WHEN JSON_EXISTS(C, '$.d[*]?(@ == 20)') THEN 1 ELSE 0 END FROM {t}",
        (),
    ),
    (
        "a filter on a key",
        """SELECT CASE WHEN JSON_EXISTS(C, '$?(@.a == 1)') THEN 1 ELSE 0 END FROM {t}""",
        (),
    ),
    ("DISTINCT on the column", "SELECT DISTINCT C FROM {t}", ()),
    ("equal to a marker", "SELECT 1 FROM {t} WHERE C = ?", (DOCUMENT,)),
    (
        "JSON_TABLE",
        "SELECT J.A FROM {t}, JSON_TABLE(C, '$' COLUMNS(A INTEGER PATH '$.a')) AS J",
        (),
    ),
)
ROOTS = (
    ("root array", "[1, 2, 3]", "$[1]"),
    ("root number", "1", "$"),
    ("root string", '"x"', "$"),
    ("root true", "true", "$"),
    ("root null", "null", "$"),
)
BUILDING = (
    ("JSON_OBJECT constant", "JSON_OBJECT('a' VALUE 1)", ()),
    ("JSON_OBJECT typed marker", "JSON_OBJECT('a' VALUE CAST(? AS INTEGER))", (1,)),
    ("JSON_OBJECT key marker", "JSON_OBJECT(KEY CAST(? AS VARCHAR(20)) VALUE 1)", ("a",)),
    ("JSON_OBJECT text marker", "JSON_OBJECT('a' VALUE CAST(? AS NVARCHAR(20)))", ("téxt",)),
    ("JSON_OBJECT NULL", "JSON_OBJECT('a' VALUE CAST(NULL AS INTEGER) NULL ON NULL)", ()),
    ("JSON_OBJECT nested", "JSON_OBJECT('a' VALUE JSON_OBJECT('b' VALUE 1))", ()),
    ("JSON_OBJECT with FORMAT JSON", "JSON_OBJECT('a' VALUE '[1, 2]' FORMAT JSON)", ()),
    ("JSON_OBJECT RETURNING", "JSON_OBJECT('a' VALUE 1 RETURNING NCLOB)", ()),
    ("JSON_ARRAY", "JSON_ARRAY(1, 'x')", ()),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for name, type_ in COLUMN_TYPES:
        _execute(conn, f"DROP TABLE {TABLE}")
        created = _execute(conn, f"CREATE TABLE {TABLE} (C {type_})")
        if created["result"] != "ok":
            _step(results, f"{name}: create", created)
            continue
        value = DOCUMENT.encode() if type_.startswith("BLOB") else DOCUMENT
        _step(
            results, f"{name}: insert", _execute(conn, f"INSERT INTO {TABLE} VALUES (?)", [value])
        )
        for key, sql, params in ON_EACH_TYPE:
            case(conn, results, f"{name}: {key}", sql.format(t=TABLE), params)
        if name == "NCLOB":
            for key, sql, params in ON_NCLOB:
                case(conn, results, key, sql.format(t=TABLE), params)
    _execute(conn, f"DROP TABLE {TABLE}")
    if _execute(conn, f"CREATE TABLE {TABLE} (C NCLOB)")["result"] == "ok":
        for key, document, path in ROOTS:
            _execute(conn, f"DELETE FROM {TABLE}")
            _step(
                results,
                f"{key}: insert",
                _execute(conn, f"INSERT INTO {TABLE} VALUES (?)", [document]),
            )
            case(
                conn,
                results,
                f"{key}: IS JSON",
                f"SELECT CASE WHEN C IS JSON THEN 1 ELSE 0 END FROM {TABLE}",
            )
            case(
                conn, results, f"{key}: JSON_VALUE", f"SELECT JSON_VALUE(C, '{path}') FROM {TABLE}"
            )
            case(
                conn,
                results,
                f"{key}: JSON_QUERY",
                f"SELECT JSON_QUERY(C, '{path}' WITH CONDITIONAL WRAPPER) FROM {TABLE}",
            )
        case(
            conn,
            results,
            "root array: its wrapper key",
            "SELECT JSON_VALUE('[1, 2]', '$.SYSIBM_ROOT_ARRAY[1]') FROM SYSIBM.SYSDUMMY1",
        )
        _execute(conn, f"DELETE FROM {TABLE}")
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?)", ["not json"])
        case(
            conn,
            results,
            "invalid document: IS JSON",
            f"SELECT CASE WHEN C IS JSON THEN 1 ELSE 0 END FROM {TABLE}",
        )
        case(
            conn,
            results,
            "invalid document: JSON_VALUE",
            f"SELECT JSON_VALUE(C, '$.a') FROM {TABLE}",
        )
    _execute(conn, f"DROP TABLE {TABLE}")
    for key, expression, params in BUILDING:
        case(conn, results, key, f"SELECT {expression} FROM SYSIBM.SYSDUMMY1", params)
    return results
