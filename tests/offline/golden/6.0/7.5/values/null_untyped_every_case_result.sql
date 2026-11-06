-- golden: values/null_untyped_every_case_result
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a"]]
-- verified: unverified
SELECT CASE WHEN "TESTAPP_AUTHOR"."NAME" = %s THEN CAST(NULL AS NVARCHAR(32)) ELSE CAST(NULL AS NVARCHAR(32)) END AS "X" FROM "TESTAPP_AUTHOR";
