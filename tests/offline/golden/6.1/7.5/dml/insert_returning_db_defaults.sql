-- golden: dml/insert_returning_db_defaults
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[5]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
SELECT "ID", "TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING" FROM FINAL TABLE (INSERT INTO "TESTAPP_DEFAULTS" ("NUMBER") VALUES (%s));
