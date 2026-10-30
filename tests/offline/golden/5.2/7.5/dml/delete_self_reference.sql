-- golden: dml/delete_self_reference
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100]]
-- verified: unverified
DELETE FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."ID" IN (SELECT U0."ID" AS "PK" FROM "TESTAPP_BOOK" U0 WHERE U0."PAGES" > %s);
