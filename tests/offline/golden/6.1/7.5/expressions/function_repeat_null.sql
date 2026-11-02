-- golden: expressions/function_repeat_null
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT REPEAT("TESTAPP_AUTHOR"."NAME", CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
