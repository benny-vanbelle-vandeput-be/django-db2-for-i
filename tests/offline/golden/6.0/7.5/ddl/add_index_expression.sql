-- golden: ddl/add_index_expression
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE INDEX "TESTAPP_BOOK_LOWER_IDX" ON "TESTAPP_BOOK" ((LOWER("TITLE")), "PAGES");
DROP INDEX "TESTAPP_BOOK_LOWER_IDX";
