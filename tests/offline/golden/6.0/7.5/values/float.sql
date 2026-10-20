-- golden: values/float
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1.5]]
-- verified: unverified
SELECT CAST(%s AS DOUBLE) AS "X" FROM "TESTAPP_AUTHOR";
