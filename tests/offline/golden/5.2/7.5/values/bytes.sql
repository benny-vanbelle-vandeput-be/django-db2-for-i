-- golden: values/bytes
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$bytes": "b25l"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-13
SELECT CAST(%s AS VARBINARY(3)) AS "X" FROM "TESTAPP_AUTHOR";
