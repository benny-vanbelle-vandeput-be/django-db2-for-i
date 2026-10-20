-- golden: queries/filter_regex
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["^A(d)a\\1?$"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE REGEXP_LIKE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(16370)));
