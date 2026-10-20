-- golden: values/string_empty
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[""]]
-- verified: unverified
SELECT CAST(%s AS NVARCHAR(32)) AS "X" FROM "TESTAPP_AUTHOR";
