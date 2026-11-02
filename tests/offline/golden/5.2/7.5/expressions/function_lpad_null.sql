-- golden: expressions/function_lpad_null
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[3, "x"]]
-- verified: unverified
SELECT LPAD(CAST(NULL AS NVARCHAR(32)), CAST(%s AS INTEGER), CAST(%s AS NVARCHAR(32))) AS "X" FROM "TESTAPP_AUTHOR";
