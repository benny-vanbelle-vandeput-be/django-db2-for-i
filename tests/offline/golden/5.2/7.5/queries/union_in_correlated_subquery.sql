-- golden: queries/union_in_correlated_subquery
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT (SELECT * FROM LATERAL ( (SELECT U0."TITLE" AS "TITLE" FROM "TESTAPP_BOOK" U0 WHERE U0."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID")) UNION (SELECT U0."TITLE" AS "TITLE" FROM "TESTAPP_BOOK" U0 WHERE U0."PAGES" > ("TESTAPP_AUTHOR"."ID")) ) ORDER BY 1 ASC FETCH FIRST 1 ROWS ONLY) AS "TITLE" FROM "TESTAPP_AUTHOR";
