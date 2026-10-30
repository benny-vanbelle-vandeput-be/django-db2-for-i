-- golden: ddl/add_index_partial_function
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE INDEX "TESTAPP_BOOK_DB2_IDX" ON "TESTAPP_BOOK" ("PAGES") WHERE UPPER("TITLE") LIKE UPPER('db2%') ESCAPE '\';
DROP INDEX "TESTAPP_BOOK_DB2_IDX";
