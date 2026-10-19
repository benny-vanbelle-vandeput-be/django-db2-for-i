-- golden: expressions/subtract_times
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[{"$time": "06:00:00"}]]
-- verified: IBM i 7.5 on PUB400, 2026-10-19
SELECT (BIGINT(MIDNIGHT_SECONDS("TESTAPP_SCHEDULE"."CLOCK") - MIDNIGHT_SECONDS(CAST(%s AS TIME))) * 1000000) AS "X" FROM "TESTAPP_SCHEDULE";
