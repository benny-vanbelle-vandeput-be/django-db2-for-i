-- golden: ddl/add_unique_constraint_expression
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
CREATE UNIQUE WHERE NOT NULL INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ" ON "TESTAPP_BOOK" ((UPPER("TITLE")));
DROP INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ";
