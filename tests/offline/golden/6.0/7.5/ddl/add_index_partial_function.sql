-- golden: ddl/add_index_partial_function
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-31
CREATE INDEX "TESTAPP_BOOK_DB2_IDX" ON "TESTAPP_BOOK" ("PAGES") WHERE UPPER("TITLE") LIKE UPPER('db2%') ESCAPE '\';
DROP INDEX "TESTAPP_BOOK_DB2_IDX";
