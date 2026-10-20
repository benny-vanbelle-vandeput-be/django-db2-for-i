-- golden: aggregates/avg_float
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
SELECT AVG("TESTAPP_DEFAULTS"."RATIO") AS "X" FROM "TESTAPP_DEFAULTS" GROUP BY "TESTAPP_DEFAULTS"."FLAG";
