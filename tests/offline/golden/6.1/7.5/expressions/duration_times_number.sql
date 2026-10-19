-- golden: expressions/duration_times_number
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[3.2]]
-- verified: IBM i 7.5 on PUB400, 2026-10-19
SELECT (BIGINT("TESTAPP_SCHEDULE"."LENGTH" * CAST(%s AS DOUBLE))) AS "X" FROM "TESTAPP_SCHEDULE";
