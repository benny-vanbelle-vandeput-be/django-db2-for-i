-- golden: dml/insert_returning_db_defaults
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_defaults
-- params: [[5]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-30
SELECT "ID", "TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING" FROM FINAL TABLE (INSERT INTO "TESTAPP_DEFAULTS" ("TEXT", "FLAG", "NUMBER", "AMOUNT", "RATIO", "DAY", "CLOCK", "STAMP", "DATA", "CODE", "NOTHING") VALUES (DEFAULT, DEFAULT, %s, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT, DEFAULT));
