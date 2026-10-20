-- golden: expressions/duration_date_plus_field
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[]]
-- verified: unverified
SELECT (CAST("TESTAPP_SCHEDULE"."DAY" AS TIMESTAMP(6)) + INTEGER(("TESTAPP_SCHEDULE"."LENGTH") / 86400000000) DAYS + MOD(("TESTAPP_SCHEDULE"."LENGTH"), 86400000000) MICROSECONDS) AS "X" FROM "TESTAPP_SCHEDULE";
