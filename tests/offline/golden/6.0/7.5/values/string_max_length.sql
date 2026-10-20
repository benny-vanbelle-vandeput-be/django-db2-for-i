-- golden: values/string_max_length
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["x"]]
-- verified: unverified
SELECT CAST(%s AS NVARCHAR(20)) AS "X" FROM "TESTAPP_AUTHOR";
