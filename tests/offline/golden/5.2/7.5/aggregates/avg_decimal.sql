-- golden: aggregates/avg_decimal
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
SELECT AVG("TESTAPP_DEFAULTS"."AMOUNT") AS "X" FROM "TESTAPP_DEFAULTS" GROUP BY "TESTAPP_DEFAULTS"."FLAG";
