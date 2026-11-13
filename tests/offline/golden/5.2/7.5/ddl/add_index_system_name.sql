-- golden: ddl/add_index_system_name
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-13
CREATE INDEX "TESTAPP_BOOK_TITLE_SYS" FOR SYSTEM NAME BOOKTTL ON "TESTAPP_BOOK" ("TITLE");
DROP INDEX "TESTAPP_BOOK_TITLE_SYS";
