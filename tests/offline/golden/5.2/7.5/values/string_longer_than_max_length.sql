-- golden: values/string_longer_than_max_length
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["abcd😀"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT CAST(%s AS NVARCHAR(32)) AS "X" FROM "TESTAPP_AUTHOR";
