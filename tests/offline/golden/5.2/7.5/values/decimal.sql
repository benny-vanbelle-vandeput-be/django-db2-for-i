-- golden: values/decimal
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "12.345"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT CAST(%s AS DECIMAL(5, 3)) AS "X" FROM "TESTAPP_AUTHOR";
