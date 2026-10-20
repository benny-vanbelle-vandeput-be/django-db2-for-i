-- golden: queries/filter_iregex
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["^ada"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE REGEXP_LIKE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(16370)), 'i');
