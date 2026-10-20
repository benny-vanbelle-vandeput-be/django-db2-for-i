-- golden: expressions/duration_times_number
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[3.2]]
-- verified: unverified
SELECT (BIGINT("TESTAPP_SCHEDULE"."LENGTH" * CAST(%s AS DOUBLE))) AS "X" FROM "TESTAPP_SCHEDULE";
