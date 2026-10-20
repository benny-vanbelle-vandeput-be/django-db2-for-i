-- golden: queries/union_in_correlated_subquery
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT (SELECT * FROM LATERAL ( (SELECT U0."TITLE" AS "TITLE" FROM "TESTAPP_BOOK" U0 WHERE U0."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID")) UNION (SELECT U0."TITLE" AS "TITLE" FROM "TESTAPP_BOOK" U0 WHERE U0."PAGES" > ("TESTAPP_AUTHOR"."ID")) ) ORDER BY 1 ASC FETCH FIRST 1 ROWS ONLY) AS "TITLE" FROM "TESTAPP_AUTHOR";
