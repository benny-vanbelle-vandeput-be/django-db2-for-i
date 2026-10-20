-- golden: queries/filter_exact_longer_than_column
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = CAST(%s AS NVARCHAR(256));
