-- golden: values/string_length
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["héllo 😀"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT CAST(%s AS NVARCHAR(8)) AS "X" FROM "TESTAPP_AUTHOR";
