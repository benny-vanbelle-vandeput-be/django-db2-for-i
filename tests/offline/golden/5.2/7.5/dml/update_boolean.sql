-- golden: dml/update_boolean
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[false, 1]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
UPDATE "TESTAPP_BOOK" SET "AVAILABLE" = %s WHERE "TESTAPP_BOOK"."ID" = %s;
