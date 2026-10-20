-- golden: dml/update_boolean
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[false, 1]]
-- verified: unverified
UPDATE "TESTAPP_BOOK" SET "AVAILABLE" = %s WHERE "TESTAPP_BOOK"."ID" = %s;
