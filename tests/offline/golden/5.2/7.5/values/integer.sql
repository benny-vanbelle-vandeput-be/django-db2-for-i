-- golden: values/integer
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1]]
-- verified: unverified
SELECT CAST(%s AS INTEGER) AS "X" FROM "TESTAPP_AUTHOR";
