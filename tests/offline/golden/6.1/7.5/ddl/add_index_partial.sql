-- golden: ddl/add_index_partial
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
CREATE INDEX "TESTAPP_BOOK_LONG_IDX" ON "TESTAPP_BOOK" ("TITLE") WHERE ("AVAILABLE" = TRUE AND "PAGES" > 100);
DROP INDEX "TESTAPP_BOOK_LONG_IDX";
