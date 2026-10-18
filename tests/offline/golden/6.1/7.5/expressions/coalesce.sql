-- golden: expressions/coalesce
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["none"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))) AS "X" FROM "TESTAPP_AUTHOR";
