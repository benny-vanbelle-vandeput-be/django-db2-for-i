-- golden: expressions/subtract_dates
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_schedule
-- params: [[{"$date": "2001-01-01"}]]
-- verified: unverified
SELECT (BIGINT(DAYS("TESTAPP_SCHEDULE"."DAY") - DAYS(CAST(%s AS DATE))) * 86400000000) AS "X" FROM "TESTAPP_SCHEDULE";
