-- golden: ddl/add_index_descending
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-26
CREATE INDEX "TESTAPP_BOOK_PUB_DESC" ON "TESTAPP_BOOK" ("PUBLISHED" DESC, "TITLE");
DROP INDEX "TESTAPP_BOOK_PUB_DESC";
