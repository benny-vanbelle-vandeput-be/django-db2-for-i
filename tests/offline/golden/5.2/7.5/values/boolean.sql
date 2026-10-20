-- golden: values/boolean
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[true]]
-- verified: unverified
SELECT CAST(%s AS BOOLEAN) AS "X" FROM "TESTAPP_AUTHOR";
