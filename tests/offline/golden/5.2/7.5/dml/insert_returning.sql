-- golden: dml/insert_returning
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["returned"]]
-- verified: unverified
SELECT "ID" FROM FINAL TABLE (INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s));
