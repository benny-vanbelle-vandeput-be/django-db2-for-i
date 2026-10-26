-- golden: ddl/add_index_descending
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE INDEX "TESTAPP_BOOK_PUB_DESC" ON "TESTAPP_BOOK" ("PUBLISHED" DESC, "TITLE");
DROP INDEX "TESTAPP_BOOK_PUB_DESC";
