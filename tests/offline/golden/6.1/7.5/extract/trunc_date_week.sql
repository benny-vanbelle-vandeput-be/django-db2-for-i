-- golden: extract/trunc_date_week
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT DATE(TRUNC_TIMESTAMP("TESTAPP_DEFAULTS"."DAY", 'IW')) AS "X" FROM "TESTAPP_DEFAULTS";
