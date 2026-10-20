-- golden: values/ip_address
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["2001::1"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT CAST(%s AS VARCHAR(39)) AS "X" FROM "TESTAPP_AUTHOR";
