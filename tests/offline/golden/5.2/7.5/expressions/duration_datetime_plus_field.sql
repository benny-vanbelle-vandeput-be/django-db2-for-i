-- golden: expressions/duration_datetime_plus_field
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[]]
-- verified: unverified
SELECT ("TESTAPP_SCHEDULE"."START" + INTEGER(("TESTAPP_SCHEDULE"."LENGTH") / 86400000000) DAYS + MOD(("TESTAPP_SCHEDULE"."LENGTH"), 86400000000) MICROSECONDS) AS "X" FROM "TESTAPP_SCHEDULE";
