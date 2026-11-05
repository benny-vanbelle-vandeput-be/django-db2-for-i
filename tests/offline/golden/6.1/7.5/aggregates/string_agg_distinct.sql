-- golden: aggregates/string_agg_distinct
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[", "]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT CASE WHEN COUNT("TESTAPP_BOOK"."TITLE") = 0 THEN NULL ELSE LISTAGG(DISTINCT CAST("TESTAPP_BOOK"."TITLE" AS NCLOB), CAST(%s AS NVARCHAR(32))) END AS "X" FROM "TESTAPP_AUTHOR" LEFT OUTER JOIN "TESTAPP_BOOK" ON ("TESTAPP_AUTHOR"."ID" = "TESTAPP_BOOK"."AUTHOR_ID") GROUP BY "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME";
