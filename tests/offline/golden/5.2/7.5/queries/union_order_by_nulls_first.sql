-- golden: queries/union_order_by_nulls_first
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[10, 100]]
-- verified: unverified
SELECT * FROM LATERAL ( (SELECT "TESTAPP_BOOK"."PUBLISHED" AS "PUBLISHED" FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."PAGES" < %s) UNION (SELECT "TESTAPP_BOOK"."PUBLISHED" AS "PUBLISHED" FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."PAGES" > %s) ) ORDER BY "PUBLISHED" IS NOT NULL, "PUBLISHED" ASC;
