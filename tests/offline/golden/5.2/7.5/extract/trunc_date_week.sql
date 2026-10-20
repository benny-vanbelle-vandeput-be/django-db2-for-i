-- golden: extract/trunc_date_week
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT DATE(TRUNC_TIMESTAMP("TESTAPP_DEFAULTS"."DAY", 'IW')) AS "X" FROM "TESTAPP_DEFAULTS";
