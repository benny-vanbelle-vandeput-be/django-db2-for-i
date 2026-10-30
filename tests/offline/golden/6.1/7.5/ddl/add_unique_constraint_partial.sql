-- golden: ddl/add_unique_constraint_partial
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE UNIQUE INDEX "TESTAPP_BOOK_TITLE_AVAIL_UNIQ" ON "TESTAPP_BOOK" ("TITLE") WHERE "AVAILABLE" = TRUE;
DROP INDEX "TESTAPP_BOOK_TITLE_AVAIL_UNIQ";
