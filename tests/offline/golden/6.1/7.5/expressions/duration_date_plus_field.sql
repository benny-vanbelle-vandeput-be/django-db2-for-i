-- golden: expressions/duration_date_plus_field
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-19
SELECT (CAST("TESTAPP_SCHEDULE"."DAY" AS TIMESTAMP(6)) + INTEGER(("TESTAPP_SCHEDULE"."LENGTH") / 86400000000) DAYS + MOD(("TESTAPP_SCHEDULE"."LENGTH"), 86400000000) MICROSECONDS) AS "X" FROM "TESTAPP_SCHEDULE";
