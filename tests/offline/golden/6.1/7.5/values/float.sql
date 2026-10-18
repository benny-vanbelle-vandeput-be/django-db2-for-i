-- golden: values/float
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1.5]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(%s AS DOUBLE) AS "X" FROM "TESTAPP_AUTHOR";
