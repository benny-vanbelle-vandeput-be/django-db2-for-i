"""Probe 02: OS release, Technology Refresh, Db2 PTF Group level, CCSIDs.

Every query runs independently: a query the user profile is not authorized to
run is reported as "unavailable" with its SQLSTATE, and the others continue.
PTF groups are selected by description, not by hard-coded group numbers.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True

QUERIES = [
    (
        "OS release (SYSIBMADM.ENV_SYS_INFO)",
        "SELECT OS_NAME, OS_VERSION, OS_RELEASE, HOST_NAME FROM SYSIBMADM.ENV_SYS_INFO",
    ),
    (
        "Technology Refresh PTF group (QSYS2.GROUP_PTF_INFO)",
        "SELECT PTF_GROUP_NAME, PTF_GROUP_DESCRIPTION, PTF_GROUP_LEVEL, PTF_GROUP_STATUS "
        "FROM QSYS2.GROUP_PTF_INFO "
        "WHERE UPPER(PTF_GROUP_DESCRIPTION) LIKE '%TECHNOLOGY REFRESH%' "
        "ORDER BY PTF_GROUP_LEVEL DESC",
    ),
    (
        "Db2 for IBM i PTF group (QSYS2.GROUP_PTF_INFO)",
        "SELECT PTF_GROUP_NAME, PTF_GROUP_DESCRIPTION, PTF_GROUP_LEVEL, PTF_GROUP_STATUS "
        "FROM QSYS2.GROUP_PTF_INFO "
        "WHERE UPPER(PTF_GROUP_DESCRIPTION) LIKE '%DB2 FOR IBM I%' "
        "ORDER BY PTF_GROUP_LEVEL DESC",
    ),
    (
        "PTFs readable at all (QSYS2.PTF_INFO)",
        "SELECT COUNT(*) AS PTFS FROM QSYS2.PTF_INFO",
    ),
    (
        "Newest applied 5770SS1 PTFs (QSYS2.PTF_INFO)",
        "SELECT PTF_IDENTIFIER, PTF_LOADED_STATUS, PTF_CREATION_TIMESTAMP "
        "FROM QSYS2.PTF_INFO WHERE PTF_PRODUCT_ID = '5770SS1' "
        "ORDER BY PTF_CREATION_TIMESTAMP DESC FETCH FIRST 3 ROWS ONLY",
    ),
    (
        "System values (QSYS2.SYSTEM_VALUE_INFO)",
        "SELECT SYSTEM_VALUE_NAME, CURRENT_NUMERIC_VALUE, CURRENT_CHARACTER_VALUE "
        "FROM QSYS2.SYSTEM_VALUE_INFO "
        "WHERE SYSTEM_VALUE_NAME IN ('QCCSID', 'QLANGID', 'QCNTRYID', 'QTIMZON', 'QUTCOFFSET')",
    ),
]

# CCSID and DEFAULT_CCSID are output columns of ACTIVE_JOB_INFO (specific name
# QSQACTJOB), found via QSYS2.SYSPARMS; GET_JOB_INFO has no CCSID column.
JOB_INFO = (
    "Job CCSID (QSYS2.ACTIVE_JOB_INFO, this job)",
    "SELECT JOB_NAME, CCSID, DEFAULT_CCSID "
    "FROM TABLE(QSYS2.ACTIVE_JOB_INFO(JOB_NAME_FILTER => '*', DETAILED_INFO => 'ALL')) X "
    "WHERE JOB_NAME = QSYS2.JOB_NAME",
)


def run(settings: Settings, conn) -> dict[str, Any]:
    queries = [run_query(conn, label, sql) for label, sql in QUERIES]
    queries.append(run_query(conn, *JOB_INFO))
    for result in queries:
        print_query(result)
    return {"queries": queries}
