-- golden: values/float
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1.5]]
-- verified: unverified
SELECT CAST(%s AS DOUBLE) AS "X" FROM "TESTAPP_AUTHOR";
