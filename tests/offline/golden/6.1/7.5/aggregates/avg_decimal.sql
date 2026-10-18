-- golden: aggregates/avg_decimal
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT AVG("TESTAPP_DEFAULTS"."AMOUNT") AS "X" FROM "TESTAPP_DEFAULTS" GROUP BY "TESTAPP_DEFAULTS"."FLAG";
