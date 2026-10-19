-- golden: values/duration
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[86400000007]]
-- verified: IBM i 7.5 on PUB400, 2026-10-19
SELECT CAST(%s AS BIGINT) AS "X" FROM "TESTAPP_AUTHOR";
