-- golden: values/string_max_length
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["x"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(%s AS NVARCHAR(20)) AS "X" FROM "TESTAPP_AUTHOR";
