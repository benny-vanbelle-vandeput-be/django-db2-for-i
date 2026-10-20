-- golden: expressions/operator_modulo
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[3]]
-- verified: unverified
SELECT (MOD("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
