"""The SQL forms Django's JSONField lookups need, for phase 6 (step 4).

``qtemp_json_functions`` showed which JSON functions work on an NCLOB; this
probe tries the forms a backend writes for ``KeyTransform`` (``data__a``) and
its lookups, as Django's Oracle code does: what ``JSON_QUERY`` and
``JSON_VALUE`` return for each JSON type (quotes on strings, spacing, JSON
null, scalars), their result types and whether they can be compared with
``=``, ``<``, ``LIKE``, ordered and grouped; a right-hand side normalized
through ``JSON_OBJECT(... FORMAT JSON)``; ``JSON_EXISTS`` with a path marker for
``has_key`` and ``isnull``; keys with quotes, ``%`` and non-ASCII text.

Writes only to QTEMP (a table that disappears with the job); reads nothing
outside it. Without commitment control (CMT=0). One connection, one statement
per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- json_lookups

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6JL"
ROWS = (
    (
        1,
        '{"a": 1, "b": "téxt \U0001f600", "c": null, "d": [10, 20, {"x": 1}], '
        '"e": {"g": [1, 2], "f": true}, "n": "1", "s": "a\'b%", "k\'%": 3, "t": true}',
    ),
    (2, '{"a": 2.5, "b": "x", "e": {"f": false}}'),
    (3, "[1, 2]"),
    (4, '"scalar"'),
    (5, None),
)

# Each: a name, an expression over C (NCLOB), its markers. SELECT K, <expr> ORDER BY K.
SELECTS: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    ("JSON_QUERY string", "JSON_QUERY(C, '$.b')", ()),
    ("JSON_QUERY number", "JSON_QUERY(C, '$.a')", ()),
    ("JSON_QUERY null", "JSON_QUERY(C, '$.c')", ()),
    ("JSON_QUERY missing", "JSON_QUERY(C, '$.z')", ()),
    ("JSON_QUERY object", "JSON_QUERY(C, '$.e')", ()),
    ("JSON_QUERY array", "JSON_QUERY(C, '$.d')", ()),
    ("JSON_QUERY boolean", "JSON_QUERY(C, '$.t')", ()),
    ("JSON_QUERY nested", "JSON_QUERY(C, '$.d[2].x')", ()),
    ("JSON_QUERY root element", "JSON_QUERY(C, '$[1]')", ()),
    ("JSON_QUERY root", "JSON_QUERY(C, '$')", ()),
    ("JSON_QUERY KEEP QUOTES", "JSON_QUERY(C, '$.b' KEEP QUOTES)", ()),
    ("JSON_QUERY OMIT QUOTES", "JSON_QUERY(C, '$.b' OMIT QUOTES)", ()),
    ("JSON_QUERY RETURNING NVARCHAR", "JSON_QUERY(C, '$.e' RETURNING NVARCHAR(4000))", ()),
    ("JSON_QUERY RETURNING NCLOB", "JSON_QUERY(C, '$.e' RETURNING NCLOB(1M))", ()),
    ("JSON_QUERY path marker", "JSON_QUERY(C, ?)", ("$.e",)),
    ("JSON_QUERY quoted key marker", "JSON_QUERY(C, ?)", ('$."k\'%"',)),
    ("JSON_QUERY non-ASCII key marker", "JSON_QUERY(C, ?)", ('$."b"',)),
    ("JSON_VALUE string", "JSON_VALUE(C, '$.b' RETURNING NVARCHAR(4000))", ()),
    ("JSON_VALUE number as text", "JSON_VALUE(C, '$.a' RETURNING NVARCHAR(4000))", ()),
    ("JSON_VALUE boolean as text", "JSON_VALUE(C, '$.t' RETURNING NVARCHAR(4000))", ()),
    ("JSON_VALUE object", "JSON_VALUE(C, '$.e' RETURNING NVARCHAR(4000))", ()),
    ("JSON_VALUE DECFLOAT", "JSON_VALUE(C, '$.a' RETURNING DECFLOAT(34))", ()),
    ("JSON_VALUE DECFLOAT of text", "JSON_VALUE(C, '$.n' RETURNING DECFLOAT(34))", ()),
    (
        "query or value",
        "COALESCE(JSON_QUERY(C, '$.e' RETURNING NVARCHAR(4000)), "
        "JSON_VALUE(C, '$.e' RETURNING NVARCHAR(4000)))",
        (),
    ),
    (
        "normalized right-hand side, object",
        "JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value')",
        ('{"g": [1, 2], "f": true}',),
    ),
    (
        "normalized right-hand side, string",
        "JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value')",
        ('"téxt"',),
    ),
    (
        "normalized right-hand side, NCLOB",
        "JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NCLOB(1M)) FORMAT JSON), '$.value')",
        ("[1, 2.50, null]",),
    ),
)

# Each: a name, a predicate over C, its markers. SELECT K WHERE <predicate> ORDER BY K.
WHERES: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    ("JSON_QUERY = marker (LOB)", "JSON_QUERY(C, '$.b') = ?", ('"x"',)),
    (
        "JSON_QUERY NVARCHAR = marker",
        "JSON_QUERY(C, '$.b' RETURNING NVARCHAR(4000)) = CAST(? AS NVARCHAR(4000))",
        ('"x"',),
    ),
    (
        "object = normalized right-hand side, other key order",
        "JSON_QUERY(C, '$.e' RETURNING NVARCHAR(4000)) = JSON_QUERY(JSON_OBJECT('value' VALUE "
        "CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value' RETURNING NVARCHAR(4000))",
        ('{"f": true, "g": [1, 2]}',),
    ),
    (
        "object = normalized right-hand side, same key order",
        "JSON_QUERY(C, '$.e' RETURNING NVARCHAR(4000)) = JSON_QUERY(JSON_OBJECT('value' VALUE "
        "CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value' RETURNING NVARCHAR(4000))",
        ('{"g": [1, 2], "f": true}',),
    ),
    (
        "number = normalized 1.0",
        "JSON_QUERY(C, '$.a' RETURNING NVARCHAR(4000)) = JSON_QUERY(JSON_OBJECT('value' VALUE "
        "CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value' RETURNING NVARCHAR(4000))",
        ("1.0",),
    ),
    ("JSON_VALUE DECFLOAT < marker", "JSON_VALUE(C, '$.a' RETURNING DECFLOAT(34)) < ?", (2,)),
    (
        "JSON_VALUE text < number (implicit cast)",
        "JSON_VALUE(C, '$.a' RETURNING NVARCHAR(4000)) < ?",
        (2,),
    ),
    (
        "JSON_VALUE text LIKE",
        "LOWER(JSON_VALUE(C, '$.b' RETURNING NVARCHAR(4000))) LIKE ? ESCAPE '\\'",
        ("%éxt%",),
    ),
    (
        "JSON_VALUE text with % LIKE",
        "JSON_VALUE(C, '$.s' RETURNING NVARCHAR(4000)) LIKE ? ESCAPE '\\'",
        ("a'b\\%",),
    ),
    ("JSON_VALUE boolean = 'true'", "JSON_VALUE(C, '$.e.f' RETURNING NVARCHAR(10)) = 'true'", ()),
    ("JSON_EXISTS marker", "JSON_EXISTS(C, ?)", ('$."c"',)),
    ("NOT JSON_EXISTS marker", "NOT JSON_EXISTS(C, ?)", ('$."c"',)),
    ("JSON_EXISTS array index", "JSON_EXISTS(C, ?)", ("$[1]",)),
    ("JSON_EXISTS nested", "JSON_EXISTS(C, ?)", ('$."d"[2]."x"',)),
    (
        "JSON null: exists and JSON_QUERY 'null'",
        "JSON_EXISTS(C, '$.c') AND JSON_QUERY(C, '$.c' RETURNING NVARCHAR(10)) = 'null'",
        (),
    ),
    ("column = marker", "C = ?", ('"scalar"',)),
    ("column = JSON null text", "C = 'null'", ()),
    (
        "JSON_QUERY IN normalized list",
        "JSON_QUERY(C, '$.a' RETURNING NVARCHAR(4000)) IN (JSON_QUERY(JSON_OBJECT('value' VALUE "
        "CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value' RETURNING NVARCHAR(4000)), "
        "JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value' "
        "RETURNING NVARCHAR(4000)))",
        ("1", "2.5"),
    ),
)

# Keys with characters a path must escape: a document of its own (row 6), each
# path spelled as Django's json.dumps writes it, without ASCII escapes, and raw.
KEYS_ROW = (
    6,
    '{"back\\\\slash": 1, "emo\U0001f921\'ji": 2, "esc\uffffape": 3, "double\\"": 4, '
    '"\u00e9t\u00e9": 5}',
)
PATHS: tuple[tuple[str, str], ...] = (
    ("backslash, json.dumps", '$."back\\\\slash"'),
    ("backslash, raw", '$."back\\slash"'),
    ("emoji, json.dumps", '$."emo\\ud83e\\udd21\'ji"'),
    ("emoji, raw", '$."emo\U0001f921\'ji"'),
    ("U+FFFF, json.dumps", '$."esc\\uffffape"'),
    ("U+FFFF, raw", '$."esc\uffffape"'),
    ("double quote, json.dumps", '$."double\\""'),
    ("double quote, doubled", '$."double"""'),
    ("e acute, json.dumps", '$."\\u00e9t\\u00e9"'),
    ("e acute, raw", '$."\u00e9t\u00e9"'),
)

# JSONObject, JSONArray and StringAgg over a key (phase 6, after the first
# db_functions run with the JSON flags on). Each: a name, an expression over K
# (INTEGER) and C (NCLOB), its markers; SELECT K, <expr> WHERE K IN (1, 2).
BUILDING: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    (
        "JSON_OBJECT, key in parentheses",
        "JSON_OBJECT((CAST(? AS NVARCHAR(32))) VALUE K RETURNING NCLOB(1M))",
        ("k",),
    ),
    ("JSON_OBJECT, key marker", "JSON_OBJECT(CAST(? AS NVARCHAR(32)) VALUE K)", ("k",)),
    ("JSON_OBJECT, KEY keyword", "JSON_OBJECT(KEY CAST(? AS NVARCHAR(32)) VALUE K)", ("k",)),
    ("JSON_OBJECT, no pairs", "JSON_OBJECT()", ()),
    ("JSON_OBJECT, no pairs, RETURNING", "JSON_OBJECT(RETURNING NCLOB(1M))", ()),
    (
        "JSON_OBJECT, NULL value",
        "JSON_OBJECT('k' VALUE CAST(NULL AS INTEGER) RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_OBJECT, NULL ON NULL",
        "JSON_OBJECT('k' VALUE CAST(NULL AS INTEGER) NULL ON NULL RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_OBJECT, nested, RETURNING NCLOB",
        "JSON_OBJECT('a' VALUE JSON_OBJECT('b' VALUE K RETURNING NCLOB(1M)) RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_OBJECT, nested, FORMAT JSON",
        "JSON_OBJECT('a' VALUE JSON_OBJECT('b' VALUE K RETURNING NCLOB(1M)) FORMAT JSON "
        "RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_OBJECT, a JSON column, FORMAT JSON",
        "JSON_OBJECT('c' VALUE C FORMAT JSON RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_OBJECT, a double marker",
        "JSON_OBJECT('d' VALUE CAST(? AS DOUBLE) RETURNING NCLOB(1M))",
        (30000.15,),
    ),
    (
        "JSON_OBJECT, a long NCLOB value",
        "JSON_OBJECT('t' VALUE CAST(? AS NCLOB(1M)) RETURNING NCLOB(1M))",
        ("x" * 4000,),
    ),
    (
        "JSON_ARRAY, NULL ON NULL",
        "JSON_ARRAY(K, CAST(NULL AS INTEGER), CAST(? AS NVARCHAR(32)) NULL ON NULL "
        "RETURNING NCLOB(1M))",
        ("x",),
    ),
    ("JSON_ARRAY, no elements", "JSON_ARRAY(RETURNING NCLOB(1M))", ()),
    (
        "JSON_ARRAY of JSON_OBJECTs",
        "JSON_ARRAY(JSON_OBJECT('a' VALUE K RETURNING NCLOB(1M)) FORMAT JSON NULL ON NULL "
        "RETURNING NCLOB(1M))",
        (),
    ),
    (
        "JSON_QUERY RETURNING NCLOB, OMIT QUOTES",
        "JSON_QUERY(C, '$.b' RETURNING NCLOB(1M) OMIT QUOTES)",
        (),
    ),
    (
        "a key of a JSON_OBJECT",
        "JSON_QUERY(JSON_OBJECT('a' VALUE K RETURNING NCLOB(1M)), '$.\"a\"')",
        (),
    ),
)
AGGREGATES: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    (
        "LISTAGG of JSON_QUERY OMIT QUOTES (CLOB)",
        "SELECT LISTAGG(JSON_QUERY(C, '$.b' OMIT QUOTES), CAST(? AS NVARCHAR(32))) FROM {t}",
        (",",),
    ),
    (
        "LISTAGG of JSON_QUERY RETURNING NCLOB OMIT QUOTES",
        "SELECT LISTAGG(JSON_QUERY(C, '$.b' RETURNING NCLOB(1M) OMIT QUOTES), "
        "CAST(? AS NVARCHAR(32))) WITHIN GROUP (ORDER BY JSON_QUERY(C, '$.b' RETURNING NCLOB(1M) "
        "OMIT QUOTES)) FROM {t}",
        (",",),
    ),
)

OTHERS: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    (
        "ORDER BY JSON_QUERY (LOB)",
        "SELECT K FROM {t} ORDER BY JSON_QUERY(C, '$.a'), K",
        (),
    ),
    (
        "ORDER BY JSON_VALUE DECFLOAT",
        "SELECT K FROM {t} ORDER BY JSON_VALUE(C, '$.a' RETURNING DECFLOAT(34)), K",
        (),
    ),
    (
        "GROUP BY JSON_QUERY NVARCHAR",
        "SELECT JSON_QUERY(C, '$.b' RETURNING NVARCHAR(4000)), COUNT(*) FROM {t} "
        "GROUP BY JSON_QUERY(C, '$.b' RETURNING NVARCHAR(4000))",
        (),
    ),
    (
        "DISTINCT JSON_QUERY (LOB)",
        "SELECT DISTINCT JSON_QUERY(C, '$.b') FROM {t}",
        (),
    ),
    (
        "JSON_OBJECT of columns",
        "SELECT JSON_OBJECT('k' VALUE K, 'c' VALUE C FORMAT JSON) FROM {t} ORDER BY K",
        (),
    ),
    (
        "describe JSON_QUERY",
        "SELECT JSON_QUERY(C, '$.e'), JSON_VALUE(C, '$.b') FROM {t} WHERE K = 1",
        (),
    ),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(conn, f"CREATE TABLE {TABLE} (K INTEGER, C NCLOB(1M))")
    results["create"] = created
    if created["result"] != "ok":
        return results
    for key, document in ROWS:
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", [key, document])
    for name, expression, params in SELECTS:
        case(conn, results, name, f"SELECT K, {expression} FROM {TABLE} ORDER BY K", params)
    for name, predicate, params in WHERES:
        case(conn, results, name, f"SELECT K FROM {TABLE} WHERE {predicate} ORDER BY K", params)
    for name, sql, params in OTHERS:
        case(conn, results, name, sql.format(t=TABLE), params)
    for name, expression, params in BUILDING:
        case(
            conn,
            results,
            name,
            f"SELECT K, {expression} FROM {TABLE} WHERE K IN (1, 2) ORDER BY K",
            params,
        )
    for name, sql, params in AGGREGATES:
        case(conn, results, name, sql.format(t=TABLE), params)
    _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", list(KEYS_ROW))
    for name, path in PATHS:
        literal = "'" + path.replace("'", "''") + "'"
        case(
            conn,
            results,
            f"key path: {name}",
            f"SELECT K, JSON_QUERY(C, {literal}) FROM {TABLE} WHERE K = 6",
        )
        case(
            conn,
            results,
            f"key path marker: {name}",
            f"SELECT K FROM {TABLE} WHERE K = 6 AND JSON_EXISTS(C, ?)",
            (path,),
        )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
