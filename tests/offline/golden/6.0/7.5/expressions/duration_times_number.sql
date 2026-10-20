-- golden: expressions/duration_times_number
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[3.2]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT (BIGINT("TESTAPP_SCHEDULE"."LENGTH" * CAST(%s AS DOUBLE))) AS "X" FROM "TESTAPP_SCHEDULE";
