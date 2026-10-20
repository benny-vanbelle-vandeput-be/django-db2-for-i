-- golden: expressions/operator_bitand
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[6]]
-- verified: unverified
SELECT (BITAND("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
