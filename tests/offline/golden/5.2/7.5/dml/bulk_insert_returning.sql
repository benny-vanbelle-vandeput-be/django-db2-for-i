-- golden: dml/bulk_insert_returning
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["one", "two", "three"]]
-- verified: unverified
SELECT "ID" FROM FINAL TABLE (INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s), (%s), (%s)) ORDER BY INPUT SEQUENCE;
