-- golden: values/string_empty
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[""]]
-- verified: unverified
SELECT CAST(%s AS NVARCHAR(32)) AS "X" FROM "TESTAPP_AUTHOR";
