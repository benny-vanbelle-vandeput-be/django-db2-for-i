-- golden: ddl/add_index_partial
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE INDEX "TESTAPP_BOOK_LONG_IDX" ON "TESTAPP_BOOK" ("TITLE") WHERE ("AVAILABLE" = TRUE AND "PAGES" > 100);
DROP INDEX "TESTAPP_BOOK_LONG_IDX";
