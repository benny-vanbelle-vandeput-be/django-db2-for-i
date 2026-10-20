-- golden: extract/trunc_date_week
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: unverified
SELECT DATE(TRUNC_TIMESTAMP("TESTAPP_DEFAULTS"."DAY", 'IW')) AS "X" FROM "TESTAPP_DEFAULTS";
