-- golden: values/integer
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT CAST(%s AS INTEGER) AS "X" FROM "TESTAPP_AUTHOR";
