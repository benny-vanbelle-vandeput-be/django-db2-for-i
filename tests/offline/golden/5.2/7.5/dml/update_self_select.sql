-- golden: dml/update_self_select
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[1, "IBM i"]]
-- verified: unverified
UPDATE "TESTAPP_BOOK" SET "PAGES" = %s WHERE "TESTAPP_BOOK"."ID" IN (SELECT U0."ID" FROM "TESTAPP_BOOK" U0 INNER JOIN "TESTAPP_AUTHOR" U1 ON (U0."AUTHOR_ID" = U1."ID") WHERE U1."NAME" = %s);
