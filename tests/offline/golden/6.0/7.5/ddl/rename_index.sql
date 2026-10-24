-- golden: ddl/rename_index
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: unverified
RENAME INDEX "TESTAPP_BOOK_TITLE_C797B345" TO "TESTAPP_BOOK_TITLE_IDX";
RENAME INDEX "TESTAPP_BOOK_TITLE_IDX" TO "TESTAPP_BOOK_TITLE_C797B345";
