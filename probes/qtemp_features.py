"""Probe 06: SQL features the capability profiles rely on.

Read-only (SYSDUMMY1 / VALUES only). Each check is one statement that either
works or fails; the result becomes evidence for a capability in
django_db2_for_i/capabilities.py:

- has_boolean_type:   BOOLEAN casts, literals, parameters, and the Python
                      type pyodbc returns;
- has_limit_offset:   LIMIT n OFFSET m (literals and parameters);
- has_offset_fetch:   OFFSET m ROWS FETCH FIRST n ROWS ONLY;
- has_json_functions: JSON_OBJECT, JSON_VALUE, JSON_TABLE;
- identifier limits:  SQLGetInfo maximum name lengths.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, run_values

NEEDS_CONNECTION = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"

CHECKS: list[tuple[str, str, str, tuple]] = [
    ("has_boolean_type", "BOOLEAN literal", f"SELECT TRUE AS T, FALSE AS F {DUMMY}", ()),
    (
        "has_boolean_type",
        "BOOLEAN cast",
        f"SELECT CAST(1 AS BOOLEAN) AS T, CAST(NULL AS BOOLEAN) AS N {DUMMY}",
        (),
    ),
    (
        "has_boolean_type",
        "BOOLEAN parameters",
        f"SELECT CAST(? AS BOOLEAN) AS T, CAST(? AS BOOLEAN) AS F {DUMMY}",
        (True, False),
    ),
    (
        "has_boolean_type",
        "BOOLEAN predicate",
        f"SELECT 1 AS ONE {DUMMY} WHERE CAST(? AS BOOLEAN) IS TRUE",
        (True,),
    ),
    (
        "has_limit_offset",
        "LIMIT/OFFSET literals",
        f"SELECT IBMREQD {DUMMY} ORDER BY IBMREQD LIMIT 1 OFFSET 0",
        (),
    ),
    (
        "has_limit_offset",
        "LIMIT/OFFSET parameters",
        f"SELECT IBMREQD {DUMMY} ORDER BY IBMREQD LIMIT ? OFFSET ?",
        (1, 0),
    ),
    (
        "has_offset_fetch",
        "OFFSET/FETCH FIRST literals",
        f"SELECT IBMREQD {DUMMY} ORDER BY IBMREQD OFFSET 0 ROWS FETCH FIRST 1 ROWS ONLY",
        (),
    ),
    (
        "has_offset_fetch",
        "OFFSET/FETCH FIRST parameters",
        f"SELECT IBMREQD {DUMMY} ORDER BY IBMREQD OFFSET ? ROWS FETCH FIRST ? ROWS ONLY",
        (0, 1),
    ),
    ("has_json_functions", "JSON_OBJECT", f"SELECT JSON_OBJECT('a' VALUE 1) AS J {DUMMY}", ()),
    (
        "has_json_functions",
        "JSON_VALUE",
        f"SELECT JSON_VALUE('{{\"a\": 1}}', '$.a' RETURNING INTEGER) AS V {DUMMY}",
        (),
    ),
    (
        "has_json_functions",
        "JSON_TABLE",
        "SELECT T.A FROM JSON_TABLE('{\"a\": 1}', '$' COLUMNS(A INTEGER PATH '$.a')) AS T",
        (),
    ),
]

GETINFO = (
    "SQL_MAX_SCHEMA_NAME_LEN",
    "SQL_MAX_TABLE_NAME_LEN",
    "SQL_MAX_COLUMN_NAME_LEN",
    "SQL_MAX_IDENTIFIER_LEN",
    "SQL_MAX_INDEX_SIZE",
    "SQL_MAX_ROW_SIZE",
    "SQL_MAX_STATEMENT_LEN",
)


def _getinfo(conn, name: str) -> Any:
    import pyodbc

    try:
        return conn.getinfo(getattr(pyodbc, name))
    except (pyodbc.Error, AttributeError) as exc:
        return f"unavailable: {exc}"


def run(settings: Settings, conn) -> dict[str, Any]:
    results = []
    for capability, label, sql, params in CHECKS:
        result = run_values(conn, f"{capability}: {label}", sql, params)
        result["capability"] = capability
        results.append(result)

    info = {name: _getinfo(conn, name) for name in GETINFO}
    print("\n# SQLGetInfo limits")
    for name, value in info.items():
        print(f"  {name:<26} {value}")

    summary: dict[str, bool] = {}
    for result in results:
        summary[result["capability"]] = summary.get(result["capability"], True) and result["ok"]
    print("\nSummary (all checks of a capability must pass)")
    for capability, ok in summary.items():
        print(f"  {capability:<20} {ok}")
    return {"checks": results, "getinfo": info, "summary": summary}
