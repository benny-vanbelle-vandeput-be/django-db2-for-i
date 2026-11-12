-- golden: values/bytes
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[{"$bytes": "b25l"}]]
-- verified: unverified
SELECT CAST(%s AS VARBINARY(3)) AS "X" FROM "TESTAPP_AUTHOR";
