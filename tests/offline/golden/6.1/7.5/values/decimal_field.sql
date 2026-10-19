-- golden: values/decimal_field
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "1.5"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT CAST(%s AS DECIMAL(10, 2)) AS "X" FROM "TESTAPP_AUTHOR";
