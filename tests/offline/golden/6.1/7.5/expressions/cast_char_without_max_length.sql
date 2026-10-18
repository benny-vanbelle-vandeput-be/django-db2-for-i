-- golden: expressions/cast_char_without_max_length
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST("TESTAPP_AUTHOR"."ID" AS NVARCHAR(16370)) AS "X" FROM "TESTAPP_AUTHOR";
