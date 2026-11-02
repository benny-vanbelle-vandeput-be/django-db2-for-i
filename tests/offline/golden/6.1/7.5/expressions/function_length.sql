-- golden: expressions/function_length
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT CHARACTER_LENGTH("TESTAPP_AUTHOR"."NAME") AS "X" FROM "TESTAPP_AUTHOR";
