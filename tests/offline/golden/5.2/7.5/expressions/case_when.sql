-- golden: expressions/case_when
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", 1, 0]]
-- verified: unverified
SELECT CASE WHEN "TESTAPP_AUTHOR"."NAME" = %s THEN CAST(%s AS INTEGER) ELSE CAST(%s AS INTEGER) END AS "X" FROM "TESTAPP_AUTHOR";
