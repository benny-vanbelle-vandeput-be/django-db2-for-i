-- golden: values/null_untyped_in_case
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", 1]]
-- verified: unverified
SELECT CASE WHEN "TESTAPP_AUTHOR"."NAME" = %s THEN CAST(%s AS INTEGER) ELSE NULL END AS "X" FROM "TESTAPP_AUTHOR";
