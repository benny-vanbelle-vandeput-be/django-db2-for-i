-- golden: values/duration
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[86400000007]]
-- verified: unverified
SELECT CAST(%s AS BIGINT) AS "X" FROM "TESTAPP_AUTHOR";
