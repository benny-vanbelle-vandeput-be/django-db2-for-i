-- golden: flush/testapp_reset_sequences
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book, ddl/create_node_fk, ddl/create_tag
-- params: [[], [], [], [], []]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
TRUNCATE TABLE "TESTAPP_AUTHOR" RESTART IDENTITY;
TRUNCATE TABLE "TESTAPP_BOOK" RESTART IDENTITY;
TRUNCATE TABLE "TESTAPP_TAG" RESTART IDENTITY;
DELETE FROM "TESTAPP_NODE";
ALTER TABLE "TESTAPP_NODE" ALTER COLUMN "ID" RESTART WITH 1;
