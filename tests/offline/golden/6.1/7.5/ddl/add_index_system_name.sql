-- golden: ddl/add_index_system_name
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
CREATE INDEX "TESTAPP_BOOK_TITLE_SYS" FOR SYSTEM NAME BOOKTTL ON "TESTAPP_BOOK" ("TITLE");
DROP INDEX "TESTAPP_BOOK_TITLE_SYS";
