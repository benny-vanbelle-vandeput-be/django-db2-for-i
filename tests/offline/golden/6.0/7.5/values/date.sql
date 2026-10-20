-- golden: values/date
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$date": "2026-10-17"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT CAST(%s AS DATE) AS "X" FROM "TESTAPP_AUTHOR";
