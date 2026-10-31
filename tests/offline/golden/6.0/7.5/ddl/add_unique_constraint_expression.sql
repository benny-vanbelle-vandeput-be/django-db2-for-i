-- golden: ddl/add_unique_constraint_expression
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[], []]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-31
CREATE UNIQUE WHERE NOT NULL INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ" ON "TESTAPP_BOOK" ((UPPER("TITLE")));
DROP INDEX "TESTAPP_BOOK_UPPER_TITLE_UNIQ";
