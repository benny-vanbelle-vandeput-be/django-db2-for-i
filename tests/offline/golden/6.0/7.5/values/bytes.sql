-- golden: values/bytes
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$bytes": "b25l"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-13
SELECT CAST(%s AS VARBINARY(3)) AS "X" FROM "TESTAPP_AUTHOR";
