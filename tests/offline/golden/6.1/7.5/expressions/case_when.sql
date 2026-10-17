-- golden: expressions/case_when
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", 1, 0]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT CASE WHEN "TESTAPP_AUTHOR"."NAME" = %s THEN CAST(%s AS INTEGER) ELSE CAST(%s AS INTEGER) END AS "X" FROM "TESTAPP_AUTHOR";
