-- golden: values/none_operand
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT ("TESTAPP_AUTHOR"."ID" + CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
