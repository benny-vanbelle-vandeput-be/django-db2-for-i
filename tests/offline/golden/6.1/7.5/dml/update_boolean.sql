-- golden: dml/update_boolean
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[false, 1]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
UPDATE "TESTAPP_BOOK" SET "AVAILABLE" = %s WHERE "TESTAPP_BOOK"."ID" = %s;
