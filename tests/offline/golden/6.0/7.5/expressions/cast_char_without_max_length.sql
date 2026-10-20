-- golden: expressions/cast_char_without_max_length
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: unverified
SELECT CAST("TESTAPP_AUTHOR"."ID" AS NVARCHAR(16370)) AS "X" FROM "TESTAPP_AUTHOR";
