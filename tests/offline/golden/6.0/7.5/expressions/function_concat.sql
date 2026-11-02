-- golden: expressions/function_concat
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["", "!", ""]]
-- verified: unverified
SELECT CONCAT(COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))), CONCAT(CAST(%s AS NVARCHAR(32)), COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))))) AS "X" FROM "TESTAPP_AUTHOR";
