-- golden: ddl/rename_index
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-24
RENAME INDEX "TESTAPP_BOOK_TITLE_C797B345" TO "TESTAPP_BOOK_TITLE_IDX";
RENAME INDEX "TESTAPP_BOOK_TITLE_IDX" TO "TESTAPP_BOOK_TITLE_C797B345";
