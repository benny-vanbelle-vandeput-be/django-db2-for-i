-- golden: expressions/subtract_dates
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[{"$date": "2001-01-01"}]]
-- verified: IBM i 7.5 on PUB400, 2026-10-19
SELECT (BIGINT(DAYS("TESTAPP_SCHEDULE"."DAY") - DAYS(CAST(%s AS DATE))) * 86400000000) AS "X" FROM "TESTAPP_SCHEDULE";
