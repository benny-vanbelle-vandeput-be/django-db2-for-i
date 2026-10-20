-- golden: expressions/duration_datetime_minus_value
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[3456000000000, 3456000000000]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT ("TESTAPP_SCHEDULE"."START" - INTEGER((CAST(%s AS BIGINT)) / 86400000000) DAYS - MOD((CAST(%s AS BIGINT)), 86400000000) MICROSECONDS) AS "X" FROM "TESTAPP_SCHEDULE";
