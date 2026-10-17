"""Write probe 10: the string encoding investigation (findings A, B and C).

Changes only QTEMP (DECLARE GLOBAL TEMPORARY TABLE SESSION.x, and for the
QAQQINI variant a job-level QAQQINI copy made by QSYS2.OVERRIDE_QAQQINI);
everything disappears when the connection closes. One connection per run;
``--all`` runs every variant in its own process, strictly one after the
other. Not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_encoding -- --variant base
    nox -s probe_encoding -- --all

Findings under investigation (docs/IBMI_NOTES.md, "Open investigation:
string encoding"):

A. Non-ASCII characters in statement text fail with HY001.
B. DEFAULT 'O''Brien' is stored as O''Brien (NVARCHAR) or garbled.
C. String parameters bound as LOB lose one character from 8185 on.

Each variant changes exactly one variable against the backend's connection
settings; every variant runs the same A, B and C checks. Step 1 facts
(versions, locale, job CCSIDs, pyodbc's type info) are recorded every run.
"""

from __future__ import annotations

import argparse
import locale
import os
import subprocess
import sys
from typing import Any

from _common import ProbeError, Settings, connect, write_result

# The backend's connection keywords (drivers/pyodbc.py), without DBQ.
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}

# variant -> (extra connection keywords, pyodbc encoding setup, extra environment)
VARIANTS: dict[str, tuple[dict[str, str], str | None, dict[str, str]]] = {
    "base": ({}, None, {}),
    "utf8_sql_char": ({}, "utf8", {}),
    "unicodesql": ({"UNICODESQL": "1"}, None, {}),
    "ccsid_1208": ({"CCSID": "1208"}, None, {}),
    "ccsid_1200": ({"CCSID": "1200"}, None, {}),
    "locale_c_utf8": ({}, None, {"LC_ALL": "C.UTF-8"}),
    "qaqqini_translate": ({}, "qaqqini", {}),
    "unicodesql_ccsid_1208": ({"UNICODESQL": "1", "CCSID": "1208"}, None, {}),
    # Follow-ups on top of utf8_sql_char (the only variant that changed A).
    "utf8_ccsid_1208": ({"CCSID": "1208"}, "utf8", {}),
    "utf8_unicodesql": ({"UNICODESQL": "1"}, "utf8", {}),
    "utf8_unicodesql_ccsid_1208": ({"UNICODESQL": "1", "CCSID": "1208"}, "utf8", {}),
    # Does the fix depend on the process locale (the driver's client codepage)?
    # LC_ALL=C also stops Python's C-locale coercion (PEP 538).
    "utf8_unicodesql_locale_c": ({"UNICODESQL": "1"}, "utf8", {"LC_ALL": "C"}),
    "utf8_unicodesql_ccsid_1208_locale_c": (
        {"UNICODESQL": "1", "CCSID": "1208"},
        "utf8",
        {"LC_ALL": "C"},
    ),
}
# Variants whose C check runs every binding mode (the others: default binding).
FULL_BINDINGS = {"base", "unicodesql"}

DUMMY = "FROM SYSIBM.SYSDUMMY1"
LENGTHS = (8184, 8185, 8186, 16370, 24555, 32768)


def error_text(exc: Exception) -> str:
    args = getattr(exc, "args", ())
    if len(args) > 1:
        return f"{args[0]} {str(args[1])[:160]}"
    return str(exc)[:200]


class Probe:
    def __init__(self, conn):
        self.conn = conn
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = (), sizes=None, fetch=True) -> dict:
        import pyodbc

        step: dict[str, Any] = {"label": label, "sql": sql if len(sql) < 300 else sql[:300]}
        cursor = self.conn.cursor()
        try:
            if sizes is not None:
                cursor.setinputsizes(sizes)
            cursor.execute(sql, params) if params else cursor.execute(sql)
            step["ok"] = True
            if fetch and cursor.description:
                step["rows"] = [tuple(row) for row in cursor.fetchall()]
        except pyodbc.Error as exc:
            step.update(ok=False, error=error_text(exc))
        except UnicodeDecodeError as exc:  # the driver returned invalid UTF-16 / UTF-8
            step.update(ok=False, error=f"decode error: {exc}"[:200])
        finally:
            cursor.close()
        self.steps.append(step)
        return step


def short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 70 else f"{text[:40]}...({len(value)} chars)"


def print_step(step: dict) -> None:
    if not step["ok"]:
        print(f"  {step['label']:<52} ERROR {step['error']}")
    elif step.get("rows") == []:
        print(f"  {step['label']:<52} (no rows)")
    elif "rows" in step:
        print(f"  {step['label']:<52} {', '.join(short(v) for v in step['rows'][0])}")
    else:
        print(f"  {step['label']:<52} ok")


# --- Step 1: facts -------------------------------------------------------------------------


def facts(probe: Probe) -> dict[str, Any]:
    import pyodbc

    conn = probe.conn
    result: dict[str, Any] = {
        "pyodbc": pyodbc.version,
        "driver_name": conn.getinfo(pyodbc.SQL_DRIVER_NAME),
        "driver_version": conn.getinfo(pyodbc.SQL_DRIVER_VER),
        "driver_odbc_version": conn.getinfo(pyodbc.SQL_DRIVER_ODBC_VER),
        "dbms_version": conn.getinfo(pyodbc.SQL_DBMS_VER),
        "maxwrite": conn.maxwrite,
        "env_LANG": os.environ.get("LANG"),
        "env_LC_ALL": os.environ.get("LC_ALL"),
        "env_LC_CTYPE": os.environ.get("LC_CTYPE"),
        "locale_LC_CTYPE": locale.setlocale(locale.LC_CTYPE),
        "codeset": locale.nl_langinfo(locale.CODESET),
    }
    type_info = {}
    cursor = conn.cursor()
    try:
        for name in ("SQL_WVARCHAR", "SQL_WLONGVARCHAR", "SQL_VARCHAR", "SQL_VARBINARY"):
            rows = cursor.getTypeInfo(getattr(pyodbc, name)).fetchall()
            # TYPE_NAME, COLUMN_SIZE by position (column name case varies with CCSID).
            type_info[name] = [(row[0], row[2]) for row in rows]
    finally:
        cursor.close()
    result["type_info"] = type_info
    job = probe.run(
        "job CCSID",
        "SELECT CCSID, DEFAULT_CCSID FROM TABLE(QSYS2.ACTIVE_JOB_INFO("
        "JOB_NAME_FILTER => '*', DETAILED_INFO => 'ALL')) X WHERE JOB_NAME = QSYS2.JOB_NAME",
    )
    result["job_ccsid"] = job.get("rows", [None])[0] if job["ok"] else job["error"]
    print("\n# step 1: facts")
    for key, value in result.items():
        print(f"  {key:<22} {value}")
    return result


# --- A: non-ASCII statement text -----------------------------------------------------------


def check_a(probe: Probe) -> dict[str, Any]:
    print("\n# A: statement text")
    cases = [
        ("ascii control", f"SELECT 'abc', HEX('abc') {DUMMY}", (), "abc"),
        ("e-acute literal", f"SELECT 'é', HEX('é') {DUMMY}", (), "é"),
        ("N e-acute euro", f"SELECT N'é€', HEX(N'é€') {DUMMY}", (), "é€"),
        ("emoji literal", f"SELECT N'\U0001f600' {DUMMY}", (), "\U0001f600"),
        ("non-ASCII in comment only", f"SELECT 'abc' {DUMMY} -- é", (), "abc"),
        ("non-ASCII alias", f"SELECT 'abc' AS \"É\" {DUMMY}", (), "abc"),
        ("prepared (with parameter)", f"SELECT 'é', CAST(? AS NVARCHAR(5)) {DUMMY}", ("x",), "é"),
        ("non-ASCII parameter (control)", f"SELECT CAST(? AS NVARCHAR(5)) {DUMMY}", ("é€",), "é€"),
    ]
    out = {}
    for label, sql, params, expected in cases:
        step = probe.run(label, sql, params)
        print_step(step)
        value = step["rows"][0][0] if step["ok"] and step.get("rows") else None
        out[label] = "ok" if value == expected else (step.get("error") or f"got {value!r}")
    return out


# --- B: escaped quote in a DEFAULT ---------------------------------------------------------


def check_b(probe: Probe) -> dict[str, Any]:
    print("\n# B: DEFAULT 'O''Brien'")
    out = {}
    literal = probe.run(
        "literal 'O''Brien' in SELECT", f"SELECT 'O''Brien', LENGTH('O''Brien') {DUMMY}"
    )
    print_step(literal)
    out["select literal"] = literal["rows"][0][0] if literal["ok"] else literal["error"]
    for index, (label, column) in enumerate(
        [
            ("NVARCHAR(20)", "NVARCHAR(20) DEFAULT 'O''Brien'"),
            ("VARCHAR(20)", "VARCHAR(20) DEFAULT 'O''Brien'"),
            ("CHAR(10)", "CHAR(10) DEFAULT 'O''Brien'"),
            ("NVARCHAR(20) non-ASCII", "NVARCHAR(20) DEFAULT 'é'"),
        ]
    ):
        table = f"SESSION.DJENCB{index}"
        created = probe.run(
            f"{label}: declare",
            f"DECLARE GLOBAL TEMPORARY TABLE {table} (K INTEGER, C {column}) "
            "ON COMMIT PRESERVE ROWS WITH REPLACE",
            fetch=False,
        )
        if not created["ok"]:
            print_step(created)
            out[label] = created["error"]
            continue
        probe.run(f"{label}: insert default", f"INSERT INTO {table} (K) VALUES (1)", fetch=False)
        probe.run(
            f"{label}: insert literal",
            f"INSERT INTO {table} (K, C) VALUES (2, 'O''Brien')",
            fetch=False,
        )
        stored = probe.run(f"{label}: stored", f"SELECT K, C FROM {table} ORDER BY K")
        rows = stored.get("rows", []) if stored["ok"] else stored["error"]
        print(f"  {label:<52} {rows}")
        out[label] = rows
    out.update(check_b_table(probe))
    return out


def check_b_table(probe: Probe) -> dict[str, Any]:
    """The same DEFAULT in a regular table (QTEMP), its catalog text, and ADD COLUMN."""
    out: dict[str, Any] = {}
    table = "QTEMP.DJENCBT"
    probe.run("B table: drop old", f"DROP TABLE {table}", fetch=False)
    created = probe.run(
        "B table: create",
        f"CREATE TABLE {table} (K INTEGER, N NVARCHAR(20) DEFAULT 'O''Brien', "
        "V VARCHAR(20) DEFAULT 'O''Brien', C CHAR(10) DEFAULT 'O''Brien')",
        fetch=False,
    )
    if not created["ok"]:
        print_step(created)
        return {"B table": created["error"]}
    added = probe.run(
        "B table: ADD COLUMN with DEFAULT",
        f"ALTER TABLE {table} ADD COLUMN A NVARCHAR(20) DEFAULT 'O''Brien'",
        fetch=False,
    )
    if not added["ok"]:
        print_step(added)
    # QTEMP tables are not journaled: WITH NC (no commitment control).
    print_step(
        probe.run("B table: insert", f"INSERT INTO {table} (K) VALUES (1) WITH NC", fetch=False)
    )
    stored = probe.run("B table: stored", f"SELECT * FROM {table}")
    print_step(stored)
    out["B table (CREATE TABLE QTEMP)"] = stored.get("rows") or stored.get("error")
    # QTEMP tables are not in QSYS2.SYSCOLUMNS, so the stored default is read back only.
    probe.run("B table: drop", f"DROP TABLE {table}", fetch=False)
    return out


# --- C: long string parameters -------------------------------------------------------------


def bindings(full: bool) -> list[tuple[str, Any]]:
    import pyodbc

    modes: list[tuple[str, Any]] = [("default", None)]
    if full:
        modes += [
            ("maxwrite=1GiB", "maxwrite"),
            ("setinputsizes WVARCHAR(n)", lambda n: [(pyodbc.SQL_WVARCHAR, n, 0)]),
            ("setinputsizes WLONGVARCHAR(n)", lambda n: [(pyodbc.SQL_WLONGVARCHAR, n, 0)]),
            ("setinputsizes WLONGVARCHAR(0) (DAE)", lambda n: [(pyodbc.SQL_WLONGVARCHAR, 0, 0)]),
        ]
    return modes


def check_c(probe: Probe, full: bool) -> dict[str, Any]:
    print("\n# C: long string parameters (server CHARACTER_LENGTH / round trip)")
    out: dict[str, Any] = {}
    targets = ("NCLOB(1M)", "DBCLOB(1M)", "CLOB(1M) CCSID 1208", "NVARCHAR(16370)")
    for mode, binding in bindings(full):
        if binding == "maxwrite":
            probe.conn.maxwrite = 1 << 30
        try:
            for target in targets:
                row = []
                for length in LENGTHS:
                    if target.startswith("NVARCHAR") and length > 16370:
                        continue
                    text = "x" * (length - 1) + "é"
                    sizes = binding(length) if callable(binding) else None
                    step = probe.run(
                        f"C {mode} {target} {length}",
                        f"SELECT CHARACTER_LENGTH(CAST(? AS {target})), "
                        f"CAST(? AS {target}) {DUMMY}",
                        (text, text),
                        sizes=(sizes * 2) if sizes else None,
                    )
                    if step["ok"]:
                        seen, back = step["rows"][0]
                        verdict = "ok" if seen == length and back == text else f"{seen}"
                        step["rows"] = [(seen, len(back) if back is not None else None)]
                    else:
                        verdict = step["error"][:40]
                    row.append(f"{length}:{verdict}")
                out[f"{mode} | {target}"] = row
                print(f"  {mode:<38} {target:<20} {' '.join(row)}")
        finally:
            probe.conn.maxwrite = 0
    return out


def check_c_multibyte(probe: Probe) -> dict[str, Any]:
    """Multi-byte texts, so chunk boundaries fall inside characters."""
    print("\n# C: multi-byte texts (round trip through NCLOB / NVARCHAR)")
    out: dict[str, Any] = {}
    for mode in ("default", "maxwrite=1GiB"):
        if mode != "default":
            probe.conn.maxwrite = 1 << 30
        try:
            for target in ("NCLOB(1M)", "NVARCHAR(16370)"):
                row = []
                for char in ("é", "€", "\U0001f600"):
                    for count in (8185, 16370, 20000):
                        text = char * count
                        units = len(text.encode("utf-16-le")) // 2
                        if target.startswith("NVARCHAR") and units > 16370:
                            continue
                        step = probe.run(
                            f"C multibyte {mode} {target} {char!a}x{count}",
                            f"SELECT CAST(? AS {target}) {DUMMY}",
                            (text,),
                        )
                        if step["ok"]:
                            back = step["rows"][0][0]
                            verdict = "ok" if back == text else f"{len(back or '')}"
                            step["rows"] = [(len(back or ""),)]
                        else:
                            verdict = step["error"][:30]
                        row.append(f"{char}x{count}:{verdict}")
                out[f"{mode} | {target}"] = row
                print(f"  {mode:<16} {target:<16} {' '.join(row)}")
        finally:
            probe.conn.maxwrite = 0
    return out


def check_c_write(probe: Probe, full: bool) -> dict[str, Any]:
    """Write into a NCLOB / BLOB column and read back; plus a server-built long value."""
    print("\n# C: write path (QTEMP table, NCLOB and BLOB columns) and read path")
    out: dict[str, Any] = {}
    table = "SESSION.DJENCC"
    created = probe.run(
        "C write: declare",
        f"DECLARE GLOBAL TEMPORARY TABLE {table} (K INTEGER, T NCLOB(1M), B BLOB(1M)) "
        "ON COMMIT PRESERVE ROWS WITH REPLACE",
        fetch=False,
    )
    if not created["ok"]:
        print_step(created)
        return {"error": created["error"]}
    modes = [("default", None)] + ([("maxwrite=1GiB", "maxwrite")] if full else [])
    key = 0
    for mode, binding in modes:
        if binding == "maxwrite":
            probe.conn.maxwrite = 1 << 30
        try:
            for length in (8184, 8185, 20000, 70000):
                key += 1
                text = "y" * (length - 1) + "€"
                data = bytes(range(256)) * (length // 256) + b"\x00" * (length % 256)
                inserted = probe.run(
                    f"C write {mode} {length}",
                    f"INSERT INTO {table} (K, T, B) VALUES (?, ?, ?)",
                    (key, text, data),
                    fetch=False,
                )
                if not inserted["ok"]:
                    out[f"{mode} {length}"] = inserted["error"]
                    print_step(inserted)
                    continue
                back = probe.run(
                    f"C read back {mode} {length}",
                    f"SELECT CHARACTER_LENGTH(T), T, LENGTH(B), B FROM {table} WHERE K = ?",
                    (key,),
                )
                seen, value, blen, blob = back["rows"][0]
                back["rows"] = [(seen, blen)]
                result = (
                    f"text {'ok' if value == text else f'server {seen}'}, "
                    f"blob {'ok' if bytes(blob) == data else f'server {blen}'}"
                )
                out[f"{mode} {length}"] = result
                print(f"  {mode:<16} {length:>6}  {result}")
        finally:
            probe.conn.maxwrite = 0
    # Read path: a long value built on the server, never sent as a parameter.
    key += 1
    probe.run(
        "C read path: server-built 40000 chars",
        # REPEAT() results above about 32K bytes are NULL; UX'20AC' is the euro sign
        # (a non-ASCII literal would hit finding A).
        f"INSERT INTO {table} (K, T) VALUES ({key}, "
        + " CONCAT ".join(["CAST(REPEAT(N'z', 8000) AS NCLOB(1M))"] * 4)
        + " CONCAT CAST(REPEAT(N'z', 7999) AS NCLOB(1M)) CONCAT UX'20AC')",
        fetch=False,
    )
    back = probe.run("C read path: read", f"SELECT T FROM {table} WHERE K = {key}")
    value = back["rows"][0][0] if back["ok"] and back.get("rows") else None
    expected = "z" * 39999 + "€"
    out["read path 40000"] = "ok" if value == expected else (back.get("error") or len(value or ""))
    back["rows"] = [(len(value),)] if value is not None else back.get("rows")
    print(f"  read path, server-built 40000 chars: {out['read path 40000']}")
    return out


# --- Variants ------------------------------------------------------------------------------


def apply_encoding(probe: Probe, setup: str | None) -> dict[str, Any]:
    import pyodbc

    info: dict[str, Any] = {"setup": setup}
    if setup == "utf8":
        probe.conn.setencoding(encoding="utf-8", ctype=pyodbc.SQL_CHAR)
        probe.conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
    elif setup == "qaqqini":
        for label, sql in [
            ("OVERRIDE_QAQQINI(1): job copy in QTEMP", "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')"),
            (
                "OVERRIDE_QAQQINI(2): SQL_TRANSLATE_ASCII_TO_JOB *YES",
                "CALL QSYS2.OVERRIDE_QAQQINI(2, 'SQL_TRANSLATE_ASCII_TO_JOB', '*YES')",
            ),
        ]:
            step = probe.run(label, sql, fetch=False)
            print_step(step)
            info[label] = step["ok"] or step["error"]
        value = probe.run(
            "QAQQINI value",
            "SELECT VARCHAR(QQVAL, 20) FROM QTEMP.QAQQINI "
            "WHERE QQPARM = 'SQL_TRANSLATE_ASCII_TO_JOB'",
        )
        print_step(value)
        info["value"] = value.get("rows") or value.get("error")
    return info


def run_variant(name: str) -> int:
    keywords, setup, _env = VARIANTS[name]
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        print(f"\n======== variant {name}: {keywords or ''} {setup or ''} {_env or ''} ========")
        conn = connect(settings, {**BACKEND, **keywords}, autocommit=True)
        probe = Probe(conn)
        result: dict[str, Any] = {"variant": name, "keywords": keywords, "environment": _env}
        result["facts"] = facts(probe)
        result["encoding"] = apply_encoding(probe, setup)
        result["A"] = check_a(probe)
        result["B"] = check_b(probe)
        full = name in FULL_BINDINGS
        result["C"] = check_c(probe, full)
        result["C_multibyte"] = check_c_multibyte(probe)
        result["C_write"] = check_c_write(probe, full)
        if setup == "qaqqini":
            probe.run("OVERRIDE_QAQQINI(3)", "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')", fetch=False)
        result["steps"] = probe.steps
        print(f"\nresult saved to {write_result(f'w10_encoding_{name}', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--variant", choices=sorted(VARIANTS))
    group.add_argument("--all", action="store_true")
    group.add_argument("--variants", help="comma-separated subset, run one after the other")
    args = parser.parse_args(argv)
    if args.variant:
        return run_variant(args.variant)
    names = args.variants.split(",") if args.variants else list(VARIANTS)
    unknown = [name for name in names if name not in VARIANTS]
    if unknown:
        parser.error(f"unknown variants: {', '.join(unknown)}")
    status = 0
    for name in names:
        env = VARIANTS[name][2]
        # One process (and one connection) per variant, strictly sequential.
        done = subprocess.run(
            [sys.executable, __file__, "--variant", name], env={**os.environ, **env}, check=False
        )
        status = status or done.returncode
        if done.returncode in (2, 3):  # unreachable / connect failed: no retry storm
            break
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
