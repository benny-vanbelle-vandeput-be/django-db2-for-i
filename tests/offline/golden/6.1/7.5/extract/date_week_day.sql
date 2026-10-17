-- golden: extract/date_week_day
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT DAYOFWEEK("TESTAPP_DEFAULTS"."DAY") AS "X" FROM "TESTAPP_DEFAULTS";
