"""DatabaseOperations: SQL generation helpers (quoting, casts, dates, pagination).

Implemented in phase 1; extended in later phases. Behaviour notes are backed
by probes (docs/IBMI_NOTES.md, ``lib_operations``).

Identifiers: Db2 for i folds unquoted names to uppercase. ``quote_name()``
uppercases and quotes every name, so ``"basic_article"`` becomes
``"BASIC_ARTICLE"``, the same object as the unquoted name. Introspection
converts names back to lowercase (``identifier_converter``). Consequence:
mixed-case ``db_table`` / ``db_column`` names are not preserved.

Date/time values are passed to the driver as ``date`` / ``time`` /
``datetime`` objects, not strings. There is no time zone aware timestamp
type: with ``USE_TZ`` aware datetimes are stored as naive values in the
connection's time zone (UTC unless the database's ``TIME_ZONE`` is set) and
made aware again when read.

Extracting date/time parts (``__year``, ``__week_day``, ``Extract()``) uses
scalar functions (probe ``extract``). Time zone rule for every date function
that takes ``tzname``: Db2 for i stores datetimes in the connection's time
zone (``connection.timezone_name``); ``tzname`` None (``USE_TZ = False``) or
equal to it needs no conversion, any other zone raises NotSupportedError.
There is no fixed-offset conversion: it would be wrong across DST changes.

Truncating (``Trunc*``, ``dates()``, ``datetimes()``) uses
``TRUNC_TIMESTAMP(<timestamp>, '<format>')`` (probe ``trunc``): ``'IW'``
starts the week on Monday as Django expects (``'WW'``, ``'W'`` and ``'DAY'``
do not). A DATE is truncated as ``DATE(TRUNC_TIMESTAMP(...))``; a TIME, which
TRUNC_TIMESTAMP does not accept, through a timestamp on 0001-01-01 (``TIME()``
first: Django passes timestamps with a TimeField output to time_trunc_sql).
"""

import datetime as dt
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable

from django.conf import settings
from django.core.management.color import no_style
from django.db import NotSupportedError
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import truncate_name
from django.utils import timezone
from django.utils.duration import duration_microseconds

from .expressions import DAY_MICROSECONDS, NVARCHAR_MAX
from .schema import default_literal

logger = logging.getLogger("django_db2_for_i")

# A DurationField is a BIGINT of microseconds.
BIGINT_MIN, BIGINT_MAX = -(2**63), 2**63 - 1

# Django lookup type -> Db2 for i function (probe ``extract``, docs/IBMI_NOTES.md).
# EXTRACT(SECOND ...) returns fractional seconds and EXTRACT has no ISODOW, so
# scalar functions are used throughout. DAYOFWEEK is 1 = Sunday .. 7 = Saturday
# and DAYOFWEEK_ISO 1 = Monday .. 7 = Sunday, Django's week_day and
# iso_week_day; WEEK_ISO is the ISO-8601 week, Django's week.
_DATE_PARTS = {
    "year": "YEAR(%s)",
    "iso_year": "INTEGER(VARCHAR_FORMAT(%s, 'IYYY'))",
    "quarter": "QUARTER(%s)",
    "month": "MONTH(%s)",
    "week": "WEEK_ISO(%s)",
    "week_day": "DAYOFWEEK(%s)",
    "iso_week_day": "DAYOFWEEK_ISO(%s)",
    "day": "DAY(%s)",
}
_TIME_PARTS = {
    "hour": "HOUR(%s)",
    "minute": "MINUTE(%s)",
    "second": "SECOND(%s)",  # whole seconds, as Django expects
}

# Django truncation kind -> TRUNC_TIMESTAMP format element (probe ``trunc``).
_DATE_TRUNC_FORMATS = {
    "year": "YEAR",
    "quarter": "Q",
    "month": "MONTH",
    "week": "IW",  # the Monday of the ISO week
    "day": "DD",
}
_TIME_TRUNC_FORMATS = {
    "hour": "HH",
    "minute": "MI",
    "second": "SS",
}


def _logged_literal(value) -> str:
    """An SQL-looking rendering of a parameter for last_executed_query() only."""
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    try:
        return default_literal(value)
    except NotSupportedError:
        return repr(value)


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = "django_db2_for_i.compiler"

    # Cast types where data_types holds more than a type (the identity clause).
    cast_data_types = {
        "AutoField": "INTEGER",
        "BigAutoField": "BIGINT",
        "SmallAutoField": "SMALLINT",
    }
    # Cast(x, CharField()) without max_length, also used by Django to order by
    # a Value: the largest NVARCHAR a cast round-trips (probe string_limits).
    cast_char_field_without_max_length = f"NVARCHAR({NVARCHAR_MAX})"

    def max_name_length(self) -> int:
        return self.connection.capabilities.max_name_length

    def quote_name(self, name: str) -> str:
        if name.startswith('"') and name.endswith('"'):
            return name  # Already quoted.
        name = truncate_name(name, self.max_name_length()).upper()
        return '"{}"'.format(name.replace('"', '""'))

    # --- Durations -----------------------------------------------------------------

    def adapt_durationfield_value(self, value):
        """Microseconds in a BIGINT; refuse durations that do not fit, before sending.

        Python's timedelta reaches 999,999,999 days, a BIGINT of microseconds
        only 2**63 - 1 (106,751,991 days); the driver would fail with an
        unclear OverflowError.
        """
        if value is None:
            return None
        # Not super(): Django's own method only exists from 6.1 (compat.py
        # routes the values here before 6.1).
        microseconds = duration_microseconds(value)
        if not BIGINT_MIN <= microseconds <= BIGINT_MAX:
            raise ValueError(
                f"Db2 for i backend: the duration {value} does not fit a DurationField "
                f"(BIGINT microseconds: at most {dt.timedelta(microseconds=BIGINT_MAX)}, "
                f"at least {dt.timedelta(microseconds=BIGINT_MIN)})."
            )
        return microseconds

    def subtract_temporals(self, internal_type, lhs, rhs):
        """Exact microseconds between two dates, times or datetimes (BIGINT).

        DAYS(), MIDNIGHT_SECONDS() and MICROSECOND() are exact over the whole
        range (probe ``durations``); TIMESTAMPDIFF assumes 30-day months and
        is never used. Each operand appears several times, so are its params.
        """
        (lhs_sql, lhs_params), (rhs_sql, rhs_params) = lhs, rhs
        days = f"BIGINT(DAYS({lhs_sql}) - DAYS({rhs_sql})) * {DAY_MICROSECONDS}"
        seconds = f"BIGINT(MIDNIGHT_SECONDS({lhs_sql}) - MIDNIGHT_SECONDS({rhs_sql})) * 1000000"
        both = (*lhs_params, *rhs_params)
        if internal_type == "DateField":
            return f"({days})", both
        if internal_type == "TimeField":
            return f"({seconds})", both
        micro = f"(MICROSECOND({lhs_sql}) - MICROSECOND({rhs_sql}))"
        return f"({days} + {seconds} + {micro})", both * 3

    def format_for_duration_arithmetic(self, sql):
        """A DurationField is a BIGINT of microseconds; expressions.py builds the
        labeled durations (DurationExpression.as_db2_for_i)."""
        return sql

    # --- Operators -----------------------------------------------------------------

    def combine_expression(self, connector, sub_expressions):
        """Db2 for i has no %, ^, &, |, #, << or >> operators (probe ``queries``).

        Shifts use exact powers of two (``BIGINT(POWER(2, n))``; POWER returns a
        DOUBLE, exact for powers of two only). ``>>`` rounds down like Python
        (-5 >> 1 = -3), which integer division (toward zero) would not; the
        division runs in DECFLOAT(34), exact for every BIGINT.
        """
        if len(sub_expressions) != 2:
            return super().combine_expression(connector, sub_expressions)
        lhs, rhs = sub_expressions
        if connector in ("&", "|", "#", "<<", ">>"):
            # F("x").bitxor(None): Db2 for i rejects an untyped NULL argument (SQL0171).
            lhs, rhs = (
                "CAST(NULL AS BIGINT)" if operand == "NULL" else operand for operand in (lhs, rhs)
            )
        functions = {"%%": "MOD", "^": "POWER", "&": "BITAND", "|": "BITOR", "#": "BITXOR"}
        if connector in functions:
            return f"{functions[connector]}({lhs}, {rhs})"
        if connector == "<<":
            return f"({lhs} * BIGINT(POWER(2, {rhs})))"
        if connector == ">>":
            return (
                f"BIGINT(FLOOR(CAST({lhs} AS DECFLOAT(34)) / "
                f"CAST(POWER(2, {rhs}) AS DECFLOAT(34))))"
            )
        return super().combine_expression(connector, sub_expressions)

    # --- Lookups -------------------------------------------------------------------

    _CASE_INSENSITIVE_LOOKUPS = frozenset({"iexact", "icontains", "istartswith", "iendswith"})

    def lookup_cast(self, lookup_type: str, internal_type: str | None = None) -> str:
        # The operators uppercase the right-hand side (see base.operators);
        # the column must be uppercased too, or the comparison stays
        # case-sensitive.
        if lookup_type in self._CASE_INSENSITIVE_LOOKUPS:
            return "UPPER(%s)"
        return "%s"

    def prep_for_iexact_query(self, x):
        """``iexact`` is ``UPPER(col) = UPPER(%s)``, not LIKE, so the value is compared
        as it is. Django's default escapes ``_``, ``%`` and ``\\`` for LIKE, which made
        ``iexact="A_b"`` look for ``A\\_B``. PostgreSQL and Oracle override it the
        same way."""
        return x

    def regex_lookup(self, lookup_type: str) -> str:
        """``regex`` / ``iregex`` as the REGEXP_LIKE predicate (ICU regular expressions).

        The pattern is a typed marker: an untyped one takes the job CCSID, so
        characters outside it fail with 22018 (probe ``queries``,
        docs/IBMI_NOTES.md). Non-string columns are cast implicitly by Db2 for i.
        """
        flags = ", 'i'" if lookup_type == "iregex" else ""
        return f"REGEXP_LIKE(%s, CAST(%s AS NVARCHAR({NVARCHAR_MAX})){flags})"

    # --- Logging ------------------------------------------------------------------

    def last_executed_query(self, cursor, sql: str, params) -> str:
        """The SQL with its parameters filled in, for logging and debugging only.

        The backend always sends parameters separately; this text is never
        executed. Strings become '...' constants (quotes doubled), None NULL,
        other values the literal of their column DEFAULT rule; a value without
        such a rule is shown with repr(). Falls back to Django's
        "QUERY = ... - PARAMS = ..." form if the SQL cannot be filled in.
        """
        if params is None:
            return sql  # sent as is: a % in it is a literal %
        if not isinstance(params, (list, tuple)):
            return super().last_executed_query(cursor, sql, params)
        try:
            return sql % tuple(_logged_literal(value) for value in params)
        except (TypeError, ValueError):
            return super().last_executed_query(cursor, sql, params)

    # --- Inserts ------------------------------------------------------------------

    def last_insert_id(self, cursor, table_name: str, pk_name: str) -> int | None:
        """The identity value of the last INSERT on this connection.

        Only reliable directly after a single-row ``INSERT ... VALUES``:
        IDENTITY_VAL_LOCAL() returns the last row's value after a multi-row
        insert and the explicit value when the key was given. Returning
        columns (``FINAL TABLE``) replace this in phase 5.
        """
        cursor.execute("SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1")
        value = cursor.fetchone()[0]
        # IDENTITY_VAL_LOCAL() is DECIMAL(31, 0).
        return None if value is None else int(value)

    # --- Pagination -----------------------------------------------------------------

    def no_limit_value(self) -> None:
        # An offset without a limit is "OFFSET n ROWS" without FETCH FIRST.
        return None

    def limit_offset_sql(self, low_mark: int | None, high_mark: int | None) -> str:
        """``OFFSET n ROWS`` and/or ``FETCH FIRST m ROWS ONLY``."""
        if not self.connection.capabilities.has_offset_fetch:
            raise NotSupportedError("Pagination needs OFFSET/FETCH FIRST (has_offset_fetch).")
        limit, offset = self._get_limit_offset_params(low_mark, high_mark)
        return " ".join(
            sql
            for sql in (
                f"OFFSET {offset} ROWS" if offset else None,
                f"FETCH FIRST {limit} ROWS ONLY" if limit else None,
            )
            if sql
        )

    # --- Extracting date/time parts ---------------------------------------------------

    def date_extract_sql(self, lookup_type, sql, params):
        return self._extract_sql(_DATE_PARTS, lookup_type, sql, params)

    def time_extract_sql(self, lookup_type, sql, params):
        return self._extract_sql(_TIME_PARTS, lookup_type, sql, params)

    def datetime_extract_sql(self, lookup_type, sql, params, tzname):
        self._check_tzname(tzname)
        return self._extract_sql(_DATE_PARTS | _TIME_PARTS, lookup_type, sql, params)

    @staticmethod
    def _extract_sql(parts, lookup_type, sql, params):
        try:
            template = parts[lookup_type]
        except KeyError:
            raise ValueError(f"Invalid lookup type: {lookup_type!r}") from None
        return template % sql, params

    # --- Truncating dates and times ---------------------------------------------------

    def date_trunc_sql(self, lookup_type, sql, params, tzname=None):
        self._check_tzname(tzname)
        fmt = self._trunc_format(_DATE_TRUNC_FORMATS, lookup_type)
        return f"DATE(TRUNC_TIMESTAMP({sql}, '{fmt}'))", params

    def datetime_trunc_sql(self, lookup_type, sql, params, tzname):
        self._check_tzname(tzname)
        fmt = self._trunc_format(_DATE_TRUNC_FORMATS | _TIME_TRUNC_FORMATS, lookup_type)
        return f"TRUNC_TIMESTAMP({sql}, '{fmt}')", params

    def time_trunc_sql(self, lookup_type, sql, params, tzname=None):
        self._check_tzname(tzname)
        fmt = self._trunc_format(_TIME_TRUNC_FORMATS, lookup_type)
        # TIME(): Django also truncates timestamps with a TimeField output here.
        time = f"TIMESTAMP(DATE('0001-01-01'), TIME({sql}))"
        return f"TIME(TRUNC_TIMESTAMP({time}, '{fmt}'))", params

    def datetime_cast_date_sql(self, sql, params, tzname):
        self._check_tzname(tzname)
        return f"DATE({sql})", params

    def datetime_cast_time_sql(self, sql, params, tzname):
        self._check_tzname(tzname)
        return f"TIME({sql})", params

    @staticmethod
    def _trunc_format(formats, lookup_type) -> str:
        try:
            return formats[lookup_type]
        except KeyError:
            raise ValueError(f"Invalid lookup type: {lookup_type!r}") from None

    def _check_tzname(self, tzname) -> None:
        """No conversion when ``tzname`` is None or the connection's zone."""
        if tzname is None or tzname == self.connection.timezone_name:
            return
        raise NotSupportedError(
            f"Db2 for i stores datetimes in the database time zone "
            f"'{self.connection.timezone_name}' (DATABASES['{self.connection.alias}']"
            f"['TIME_ZONE']); converting them to '{tzname}' is not supported yet. Use the "
            "same zone for Django's TIME_ZONE (or the tzinfo argument) and the database."
        )

    # --- Date/time values -------------------------------------------------------------

    def adapt_datefield_value(self, value):
        return value

    def adapt_datetimefield_value(self, value):
        if value is None or hasattr(value, "resolve_expression"):
            return value
        if timezone.is_aware(value):
            if not settings.USE_TZ:
                raise ValueError(
                    "Db2 for i backend does not support timezone-aware datetimes when "
                    "USE_TZ is False."
                )
            value = timezone.make_naive(value, self.connection.timezone)
        return value

    def adapt_timefield_value(self, value):
        """A ``time`` without microseconds.

        Db2 for i ``TIME`` has no fractional seconds and drops them silently
        (docs/DECISIONS.md). Truncating here makes saving and lookups such as
        ``filter(t=value)`` consistent with what is stored.
        """
        if value is None or hasattr(value, "resolve_expression"):
            return value
        if timezone.is_aware(value):
            raise ValueError("Django does not support timezone-aware times.")
        return value.replace(microsecond=0)

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == "DateTimeField" and settings.USE_TZ:
            converters.append(self.convert_datetimefield_value)
        elif internal_type == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_datetimefield_value(self, value, expression, connection):
        if value is not None:
            value = timezone.make_aware(value, self.connection.timezone)
        return value

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None:
            value = uuid.UUID(value)
        return value

    # --- Transactions and savepoints ----------------------------------------------

    def start_transaction_sql(self):
        """No statement: under commitment control a transaction starts with the
        first statement (lib_rollback_ddl). Db2 for i has no BEGIN, BEGIN WORK
        or START TRANSACTION (SQL0104 / SQL0199, probe transaction_start); this
        is what ``sqlmigrate`` prints before an atomic migration."""
        return ""

    def savepoint_create_sql(self, sid):
        """The ON ROLLBACK clause is required on Db2 for i (SQL0104 without it).

        RETAIN CURSORS keeps open cursors usable after ROLLBACK TO SAVEPOINT
        (RETAIN LOCKS is not valid). RELEASE and ROLLBACK TO use Django's
        defaults (probe ``probe_savepoints``, docs/IBMI_NOTES.md).
        """
        return f"SAVEPOINT {self.quote_name(sid)} ON ROLLBACK RETAIN CURSORS"

    # --- Identity reset ----------------------------------------------------------

    def sequence_reset_sql(self, style, model_list):
        """Restart each model's identity at ``MAX(pk) + 1`` (1 for an empty table).

        ``GENERATED BY DEFAULT`` identities do not advance past explicit key
        values (e.g. from fixtures), so the next generated key would collide.
        ``RESTART WITH`` needs a constant, so the maximum is queried first.

        Inside an atomic block the ``ALTER TABLE`` would fail with SQL0910
        (pending changes on the table, e.g. rows just loaded by ``loaddata``),
        so the reset is deferred until after the commit and no SQL is returned.
        Known gap: in Django's ``TestCase`` the transaction is never committed,
        so the deferred reset never runs there.
        """
        if self.connection.in_atomic_block:
            models = list(model_list)
            self._after_transaction(
                lambda: self._execute(self._identity_reset_statements(no_style(), models)),
                "sequence reset for " + ", ".join(m._meta.db_table for m in models),
            )
            return []
        return self._identity_reset_statements(style, model_list)

    def _identity_reset_statements(self, style, model_list) -> list[str]:
        from django.db import models

        statements = []
        for model in model_list:
            for field in model._meta.local_fields:
                if isinstance(field, models.AutoField):
                    table, column = model._meta.db_table, field.column
                    statements.append(
                        "{} {} {} {} {}".format(
                            style.SQL_KEYWORD("ALTER TABLE"),
                            style.SQL_TABLE(self.quote_name(table)),
                            style.SQL_KEYWORD("ALTER COLUMN"),
                            style.SQL_FIELD(self.quote_name(column)),
                            style.SQL_KEYWORD(
                                f"RESTART WITH {self._next_identity_value(table, column)}"
                            ),
                        )
                    )
                    break  # Only one AutoField per model.
        return statements

    def _next_identity_value(self, table: str, column: str) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COALESCE(MAX({self.quote_name(column)}), 0) + 1 "
                f"FROM {self.quote_name(table)}"
            )
            return int(cursor.fetchone()[0])

    def _execute(self, statements: list[str]) -> None:
        with self.connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)

    def _after_transaction(self, func, description: str) -> None:
        """Run ``func`` now, or after the commit if an atomic block is active.

        For identity restarts (``ALTER TABLE``), which fail with SQL0910 in a
        transaction that has pending changes on the table. Never uses a
        second connection. If the outer transaction is rolled back (or never
        committed, as in ``TestCase``), ``func`` does not run; the DEBUG log
        line lets IntegrityErrors from colliding keys be traced back to it.
        """
        if self.connection.in_atomic_block:
            logger.debug(
                "Identity restart deferred until commit (SQL0910) on database '%s': %s",
                self.connection.alias,
                description,
            )
            self.connection.on_commit(func)
        else:
            func()

    # --- Flush ----------------------------------------------------------------------

    def execute_sql_flush(self, sql_list):
        """Empty the tables, then restart identities outside the transaction.

        Django's version runs everything in one atomic block; an identity
        restart after a DELETE in the same transaction fails with SQL0910.
        """
        restarts = [sql for sql in sql_list if _is_identity_restart(sql)]
        super().execute_sql_flush([sql for sql in sql_list if not _is_identity_restart(sql)])
        if restarts:
            self._after_transaction(
                lambda: self._execute(restarts), "flush: " + "; ".join(restarts)
            )

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        """Empty ``tables``.

        ``TRUNCATE`` is refused for a table referenced by a foreign key
        (SQ20356, even when the child is empty), so those tables are emptied
        with ``DELETE`` after their children, and their identity is restarted
        with ``ALTER TABLE ... ALTER COLUMN ... RESTART WITH <start>``.
        Other tables use ``TRUNCATE TABLE ... [RESTART IDENTITY]``.
        """
        if not tables:
            return []
        names = {table.upper(): table for table in tables}
        references, identities = self._flush_metadata(list(names))

        def table_sql(name: str) -> str:
            return style.SQL_FIELD(self.quote_name(names[name]))

        parents = {parent for _, parent in references}
        statements = [
            "{} {}{}".format(
                style.SQL_KEYWORD("TRUNCATE TABLE"),
                table_sql(name),
                style.SQL_KEYWORD(" RESTART IDENTITY") if reset_sequences else "",
            )
            for name in names
            if name not in parents
        ]
        for name in children_first(parents, references):
            statements.append(f"{style.SQL_KEYWORD('DELETE FROM')} {table_sql(name)}")
            if reset_sequences and name in identities:
                column, start = identities[name]
                statements.append(
                    "{} {} {} {} {}".format(
                        style.SQL_KEYWORD("ALTER TABLE"),
                        table_sql(name),
                        style.SQL_KEYWORD("ALTER COLUMN"),
                        style.SQL_FIELD(self.quote_name(column)),
                        style.SQL_KEYWORD(f"RESTART WITH {start}"),
                    )
                )
        return statements

    def _flush_metadata(
        self, tables: list[str]
    ) -> tuple[set[tuple[str, str]], dict[str, tuple[str, int]]]:
        """Foreign keys among ``tables`` and their identity columns.

        Returns ``({(child, parent), ...}, {table: (identity column, start)})``
        with uppercase names, for tables in the connection's current schema.
        """
        placeholders = ", ".join(["%s"] * len(tables))
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT C.TABLE_NAME, P.TABLE_NAME "
                "FROM QSYS2.SYSREFCST R "
                "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
                "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
                "JOIN QSYS2.SYSCST P ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
                "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
                f"WHERE P.TABLE_SCHEMA = CURRENT SCHEMA AND P.TABLE_NAME IN ({placeholders})",
                tables,
            )
            references = {(child.rstrip(), parent.rstrip()) for child, parent in cursor.fetchall()}
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, IDENTITY_START FROM QSYS2.SYSCOLUMNS "
                "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND IS_IDENTITY = 'YES' "
                f"AND TABLE_NAME IN ({placeholders})",
                tables,
            )
            identities = {
                table.rstrip(): (column.rstrip(), int(start))
                for table, column, start in cursor.fetchall()
            }
        return references, identities


def _is_identity_restart(sql: str) -> bool:
    """True for the ``ALTER TABLE ... RESTART WITH`` statements of sql_flush()."""
    return sql.lstrip().upper().startswith("ALTER TABLE")


def children_first(tables: Iterable[str], references: set[tuple[str, str]]) -> list[str]:
    """Order ``tables`` so that a table comes before the tables it references.

    Self-references are ignored (one DELETE removes all rows). Cycles are
    broken in name order; such a DELETE may then fail on a constraint.
    """
    remaining = set(tables)
    children_of: dict[str, set[str]] = defaultdict(set)
    for child, parent in references:
        if child != parent and child in remaining and parent in remaining:
            children_of[parent].add(child)
    ordered: list[str] = []
    while remaining:
        # Ready: no child of this table is still waiting to be emptied.
        ready = sorted(t for t in remaining if not (children_of[t] & remaining))
        ready = ready or [min(remaining)]
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered
