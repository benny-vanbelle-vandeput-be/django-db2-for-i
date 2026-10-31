-- golden: ddl/add_index_expression
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
CREATE INDEX "TESTAPP_BOOK_LOWER_IDX" ON "TESTAPP_BOOK" ((LOWER("TITLE")), "PAGES");
DROP INDEX "TESTAPP_BOOK_LOWER_IDX";
