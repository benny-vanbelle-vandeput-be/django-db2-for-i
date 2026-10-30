-- golden: dml/bulk_insert
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["one", "two", "three"]]
-- verified: unverified
INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s), (%s), (%s);
