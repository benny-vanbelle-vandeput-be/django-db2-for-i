-- golden: values/bigint
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1099511627776]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(%s AS BIGINT) AS "X" FROM "TESTAPP_AUTHOR";
