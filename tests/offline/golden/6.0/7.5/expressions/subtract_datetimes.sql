-- golden: expressions/subtract_datetimes
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[{"$datetime": "2026-01-31T01:00:00.000002"}, {"$datetime": "2026-01-31T01:00:00.000002"}, {"$datetime": "2026-01-31T01:00:00.000002"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT (BIGINT(DAYS("TESTAPP_SCHEDULE"."START") - DAYS(CAST(%s AS TIMESTAMP(6)))) * 86400000000 + BIGINT(MIDNIGHT_SECONDS("TESTAPP_SCHEDULE"."START") - MIDNIGHT_SECONDS(CAST(%s AS TIMESTAMP(6)))) * 1000000 + (MICROSECOND("TESTAPP_SCHEDULE"."START") - MICROSECOND(CAST(%s AS TIMESTAMP(6))))) AS "X" FROM "TESTAPP_SCHEDULE";
