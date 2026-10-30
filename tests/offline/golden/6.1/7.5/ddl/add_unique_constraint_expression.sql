-- golden: ddl/add_unique_constraint_expression
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE UNIQUE INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ" ON "TESTAPP_BOOK" ((UPPER("TITLE")));
DROP INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ";
