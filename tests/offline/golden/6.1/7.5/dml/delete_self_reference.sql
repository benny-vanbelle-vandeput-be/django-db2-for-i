-- golden: dml/delete_self_reference
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
DELETE FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."ID" IN (SELECT "U0"."ID" AS "PK" FROM "TESTAPP_BOOK" "U0" WHERE "U0"."PAGES" > %s);
