-- golden: queries/case_when_exists
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[1, 0]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT CASE WHEN ((SELECT (1) AS "A" FROM "TESTAPP_BOOK" U0 WHERE U0."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") FETCH FIRST 1 ROWS ONLY) IS NOT NULL) THEN CAST(%s AS INTEGER) ELSE CAST(%s AS INTEGER) END AS "X" FROM "TESTAPP_AUTHOR";
