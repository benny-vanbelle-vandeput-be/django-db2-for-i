-- golden: expressions/coalesce
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["none"]]
-- verified: unverified
SELECT COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))) AS "X" FROM "TESTAPP_AUTHOR";
