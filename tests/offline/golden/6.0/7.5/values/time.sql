-- golden: values/time
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$time": "01:02:03"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT CAST(%s AS TIME) AS "X" FROM "TESTAPP_AUTHOR";
