"""Write probe 12: the backend's connection in a non-UTF-8 process locale.

Changes only QTEMP (DECLARE GLOBAL TEMPORARY TABLE SESSION.x). One
connection per run, opened by the backend itself (Django settings
``tests.django_settings.settings_ibmi``), so the driver defaults are the
real ones. ``--all`` runs each locale in its own process, one after the
other. Not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_locale -- --all

Questions (fix A follow-up, docs/IBMI_NOTES.md):
1. Are data values correct when the process runs with LC_ALL=C?
2. Does pyodbc setdecoding(SQL_WMETADATA, ...) fix result column names and
   error messages under LC_ALL=C?
"""

from __future__ import annotations

import argparse
import locale
import os
import subprocess
import sys
from typing import Any

from _common import write_result

LOCALES = {"default": {}, "c": {"LC_ALL": "C"}}
TEXT = "é€\U0001f600"
DUMMY = "FROM SYSIBM.SYSDUMMY1"
TABLE = "SESSION.DJLOC"
# Metadata decodings to try (None: pyodbc's default, UTF-16LE).
METADATA_DECODINGS = (None, "utf-8", "latin-1")


def values(cursor) -> dict[str, Any]:
    """Data values: literals and parameters, into and out of several column types."""
    out: dict[str, Any] = {}
    cursor.execute(f"SELECT N'{TEXT}', 'éÄß' {DUMMY}")
    out["literals"] = cursor.fetchone() == (TEXT, "éÄß")
    cursor.execute(
        f"DECLARE GLOBAL TEMPORARY TABLE {TABLE} (K INTEGER, V VARCHAR(10), N NVARCHAR(10), "
        "L NCLOB(1K)) ON COMMIT PRESERVE ROWS WITH REPLACE"
    )
    cursor.execute(f"INSERT INTO {TABLE} VALUES (1, %s, %s, %s)", ["éÄß", TEXT, TEXT])
    cursor.execute(f"INSERT INTO {TABLE} VALUES (2, 'éÄß', N'{TEXT}', N'{TEXT}')")
    cursor.execute(f"SELECT V, N, L FROM {TABLE} ORDER BY K")
    rows = cursor.fetchall()
    out["rows"] = [list(map(repr, row)) for row in rows]
    out["round_trip"] = rows == [("éÄß", TEXT, TEXT)] * 2
    cursor.execute(f"DROP TABLE {TABLE}")
    return out


def metadata(cursor) -> dict[str, Any]:
    from django.db import DatabaseError

    try:
        cursor.execute(f'SELECT 1 AS "ÄÖÜ" {DUMMY}')
        name = cursor.description[0][0]
    except UnicodeDecodeError as exc:  # pyodbc decodes the name with the metadata encoding
        name = f"decode error: {exc}"
    try:
        cursor.execute('SELECT * FROM QTEMP."ÄÖÜX"')
        message = ""
    except DatabaseError as exc:
        message = str(exc)
    except Exception as exc:  # pyodbc may fail to build the error (SystemError)
        message = f"{type(exc).__name__}: {exc}"
    return {
        "column_name": repr(name),
        "column_name_ok": name == "ÄÖÜ",
        "message": message[:160],
        "message_ok": '"ÄÖÜX" in QTEMP' in message,
    }


def run_locale(name: str) -> int:
    import django
    import pyodbc

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.django_settings.settings_ibmi")
    django.setup()
    from django.db import connection

    result: dict[str, Any] = {
        "locale": name,
        "LC_ALL": os.environ.get("LC_ALL"),
        "LC_CTYPE": locale.setlocale(locale.LC_CTYPE),
        "codeset": locale.nl_langinfo(locale.CODESET),
    }
    print(f"\n======== locale {name}: {result['LC_CTYPE']} ({result['codeset']}) ========")
    try:
        connection.ensure_connection()
        raw = connection.connection._raw
        with connection.cursor() as cursor:
            result["values"] = values(cursor)
            print(f"  data values round trip: {result['values']['round_trip']}")
            for row in result["values"]["rows"]:
                print(f"    {row}")
            result["metadata"] = {}
            for encoding in METADATA_DECODINGS:
                if encoding is not None:
                    raw.setdecoding(pyodbc.SQL_WMETADATA, encoding=encoding)
                found = metadata(cursor)
                result["metadata"][str(encoding)] = found
                print(
                    f"  metadata decoding {encoding!s:<8} name {found['column_name']:<14} "
                    f"ok={found['column_name_ok']!s:<5} message ok={found['message_ok']!s:<5} "
                    f"{found['message'][:70]!r}"
                )
    finally:
        connection.close()
    path = write_result(f"lib_locale_{name}", result, _settings())
    print(f"\nresult saved to {path}")
    return 0


def _settings():
    from _common import Settings

    return Settings.from_env(need_credentials=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--locale", choices=sorted(LOCALES))
    group.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.locale:
        return run_locale(args.locale)
    status = 0
    for name, env in LOCALES.items():
        # One process (and one connection) per locale, strictly sequential.
        done = subprocess.run(
            [sys.executable, __file__, "--locale", name], env={**os.environ, **env}, check=False
        )
        status = status or done.returncode
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
