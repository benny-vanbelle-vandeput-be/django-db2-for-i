-- golden: flush/testapp_reset_sequences
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book, ddl/create_node_fk, ddl/create_tag
-- params: [[], [], [], [], [], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-25
TRUNCATE TABLE "TESTAPP_BOOK" RESTART IDENTITY;
DELETE FROM "TESTAPP_AUTHOR";
ALTER TABLE "TESTAPP_AUTHOR" ALTER COLUMN "ID" RESTART WITH 1;
DELETE FROM "TESTAPP_NODE";
ALTER TABLE "TESTAPP_NODE" ALTER COLUMN "ID" RESTART WITH 1;
DELETE FROM "TESTAPP_TAG";
