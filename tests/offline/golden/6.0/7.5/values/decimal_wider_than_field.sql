-- golden: values/decimal_wider_than_field
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$decimal": "123456.789"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-13
SELECT CAST(%s AS DECIMAL(9, 3)) AS "X" FROM "TESTAPP_AUTHOR";
