-- golden: extract/date_week_day
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
SELECT DAYOFWEEK("TESTAPP_DEFAULTS"."DAY") AS "X" FROM "TESTAPP_DEFAULTS";
