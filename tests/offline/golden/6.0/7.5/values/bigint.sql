-- golden: values/bigint
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1099511627776]]
-- verified: unverified
SELECT CAST(%s AS BIGINT) AS "X" FROM "TESTAPP_AUTHOR";
