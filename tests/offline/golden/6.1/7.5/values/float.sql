-- golden: values/float
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1.5]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT CAST(%s AS DOUBLE) AS "X" FROM "TESTAPP_AUTHOR";
