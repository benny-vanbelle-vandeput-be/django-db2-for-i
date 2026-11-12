-- golden: values/none_operand
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT ("TESTAPP_AUTHOR"."ID" + CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
